"""Local NLI grounding: score each claim's entailment against the source documents with a
dedicated transformer NLI model (spec §6: MiniCheck/AlignScore) instead of an LLM judge.

This is the real scoring handler the design intended — no API, no rate limits, graded 0..1. It is
built for the two-machine reality:

* **CUDA here** (``TorchBackend`` auto-selects cuda→cpu, fp16 on GPU).
* **Intel GPU on the other box** (``OpenVinoBackend`` via ``optimum-intel``, ``device="GPU"``) — same
  interface, selected by env (``AAH_NLI_BACKEND=openvino``), so nothing else changes.

Speed/caching is first-class because these models are slow on a weak device:

* the model + tokenizer load **once** (process singleton);
* long source docs are **windowed** (tokenizer-aware, with overlap + a chunk cap);
* a claim's score = **max entailment over its chunks** (supported by *some* passage);
* results are cached by ``(model, claim, context-hash)`` so re-renders are free;
* :meth:`LocalNli.warm` scores every claim×chunk pair in **batched** passes up front, turning the
  per-claim injection calls into cache hits.

The public entry point is :func:`grounding_scorer`, which returns an async
``(claim, response, context) -> float`` — the exact ``Scorer`` the claim-extraction pipeline injects.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import threading
from dataclasses import dataclass
from typing import Optional, Sequence

_ENTAIL_KEYS = ("entail",)          # substring match against id2label values (case-insensitive)


@dataclass(frozen=True)
class NliConfig:
    model: str = os.environ.get("AAH_NLI_MODEL", "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli")
    backend: str = os.environ.get("AAH_NLI_BACKEND", "torch")     # torch | openvino
    device: str = os.environ.get("AAH_NLI_DEVICE", "auto")        # torch: auto|cuda|cpu ; ov: GPU|CPU|AUTO
    max_length: int = int(os.environ.get("AAH_NLI_MAX_LEN", "512"))
    batch_size: int = int(os.environ.get("AAH_NLI_BATCH", "16"))
    max_chunks: int = int(os.environ.get("AAH_NLI_MAX_CHUNKS", "12"))
    stride: int = int(os.environ.get("AAH_NLI_STRIDE", "64"))      # token overlap between windows


# --- backends -----------------------------------------------------------------------
def _select_torch_device(torch, want: str) -> str:
    """Pick the torch device: cuda (NVIDIA), xpu (Intel GPU via IPEX), or cpu. ``auto`` prefers
    cuda→xpu→cpu; an explicit device that isn't available raises rather than silently downgrading."""
    want = (want or "auto").lower()
    if want in ("auto", "cuda") and torch.cuda.is_available():
        return "cuda"
    if want in ("auto", "xpu"):
        try:
            import intel_extension_for_pytorch  # noqa: F401 — registers torch.xpu on Intel GPUs
        except Exception:
            pass
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return "xpu"
    if want == "cuda":
        raise RuntimeError("AAH_NLI_DEVICE=cuda but no CUDA device is available")
    if want == "xpu":
        raise RuntimeError("AAH_NLI_DEVICE=xpu but no XPU device is available "
                           "(is intel_extension_for_pytorch installed and the Intel GPU driver present?)")
    return "cpu"


class _TorchBackend:
    """``transformers`` NLI on CUDA (NVIDIA), XPU (Intel GPU via IPEX), or CPU.

    HuggingFace-free operation: point ``AAH_NLI_MODEL`` at a **local folder** and it loads with
    ``local_files_only=True`` — it never contacts huggingface.co (for blocked machines: copy the
    model folder over, or set ``HF_ENDPOINT`` to a mirror). Installing the ``transformers`` *package*
    is from PyPI and needs no HF access.
    """

    def __init__(self, cfg: NliConfig):
        import os

        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.device = _select_torch_device(torch, cfg.device)
        local = os.path.isdir(cfg.model)          # a local path -> never reach for the hub
        self._tok = AutoTokenizer.from_pretrained(cfg.model, local_files_only=local)
        self._model = AutoModelForSequenceClassification.from_pretrained(cfg.model, local_files_only=local)
        self._model.to(self.device).eval()
        self._fp16 = self.device in ("cuda", "xpu")
        if self._fp16:
            self._model.half()
        self._entail_idx = _entailment_index(self._model.config)
        self.tokenizer = self._tok

    def predict(self, pairs: Sequence[tuple[str, str]], max_length: int) -> list[float]:
        """Entailment probability for each (premise, hypothesis) pair."""
        torch = self._torch
        enc = self._tok([p for p, _ in pairs], [h for _, h in pairs],
                        padding=True, truncation="only_first", max_length=max_length,
                        return_tensors="pt").to(self.device)
        with torch.no_grad():
            logits = self._model(**enc).logits.float()
        probs = torch.softmax(logits, dim=-1)[:, self._entail_idx]
        return [float(x) for x in probs.cpu().tolist()]


class _OpenVinoBackend:
    """Intel-GPU / CPU NLI via optimum-intel (OpenVINO). For the machine with no CUDA.

    Enable with ``AAH_NLI_BACKEND=openvino`` and ``pip install "optimum[openvino]"``; the first load
    exports the model to OpenVINO IR (cached by optimum). ``device`` is an OpenVINO device string
    (``GPU`` for the Intel iGPU, ``CPU``, or ``AUTO``).
    """

    def __init__(self, cfg: NliConfig):
        from optimum.intel import OVModelForSequenceClassification  # type: ignore
        from transformers import AutoTokenizer

        self.device = cfg.device if cfg.device.lower() != "auto" else "AUTO"
        self._tok = AutoTokenizer.from_pretrained(cfg.model)
        self._model = OVModelForSequenceClassification.from_pretrained(
            cfg.model, export=True, device=self.device
        )
        self._entail_idx = _entailment_index(self._model.config)
        self.tokenizer = self._tok

    def predict(self, pairs: Sequence[tuple[str, str]], max_length: int) -> list[float]:
        import numpy as np

        enc = self._tok([p for p, _ in pairs], [h for _, h in pairs],
                        padding=True, truncation="only_first", max_length=max_length,
                        return_tensors="np")
        logits = self._model(**enc).logits
        e = np.exp(logits - logits.max(axis=-1, keepdims=True))
        probs = e / e.sum(axis=-1, keepdims=True)
        return [float(x) for x in probs[:, self._entail_idx]]


def _entailment_index(config) -> int:
    """Find the 'entailment' class index from the model's id2label (order varies by model)."""
    id2label = getattr(config, "id2label", None) or {}
    for idx, label in id2label.items():
        if any(k in str(label).lower() for k in _ENTAIL_KEYS):
            return int(idx)
    # MNLI convention fallback: [contradiction, neutral, entailment] -> last, else 0
    return (len(id2label) - 1) if id2label else 0


def _make_backend(cfg: NliConfig):
    if cfg.backend.lower() == "openvino":
        return _OpenVinoBackend(cfg)
    return _TorchBackend(cfg)


# --- chunking -----------------------------------------------------------------------
def _chunk(tokenizer, text: str, cfg: NliConfig) -> list[str]:
    """Tokenizer-aware overlapping windows of the context, decoded back to text, capped."""
    text = (text or "").strip()
    if not text:
        return []
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    window = max(64, cfg.max_length - 96)          # leave room for the hypothesis + specials
    # clamp overlap to < window so the step never collapses to 1 (which would over-chunk tiny windows)
    step = max(1, window - min(cfg.stride, window // 2))
    chunks: list[str] = []
    for start in range(0, len(ids), step):
        piece = ids[start:start + window]
        if not piece:
            break
        chunks.append(tokenizer.decode(piece, skip_special_tokens=True))
        if len(chunks) >= cfg.max_chunks or start + window >= len(ids):
            break
    return chunks or [text]


def _hash(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:16]


# --- the scorer ---------------------------------------------------------------------
class LocalNli:
    """Cached, batched local NLI grounding scorer. Thread-safe lazy load; process-wide reuse."""

    def __init__(self, cfg: Optional[NliConfig] = None):
        self.cfg = cfg or NliConfig()
        self._backend = None
        self._lock = threading.Lock()
        self._chunk_cache: dict[str, list[str]] = {}
        self._score_cache: dict[tuple[str, str], float] = {}

    def _get_backend(self):
        if self._backend is None:
            with self._lock:
                if self._backend is None:
                    self._backend = _make_backend(self.cfg)
        return self._backend

    def _chunks_for(self, context: str) -> list[str]:
        key = _hash(context)
        if key not in self._chunk_cache:
            self._chunk_cache[key] = _chunk(self._get_backend().tokenizer, context, self.cfg)
        return self._chunk_cache[key]

    def warm(self, claims: Sequence[str], context: str) -> None:
        """Pre-score every (claim × chunk) pair in batched passes and fill the cache.

        Call this once before the per-claim injection calls so those become cache hits — the big
        speed win when the model is slow. Uncached claims only."""
        chunks = self._chunks_for(context)
        ctx_h = _hash(context)
        todo = [c for c in dict.fromkeys(claims) if (c, ctx_h) not in self._score_cache]
        if not chunks or not todo:
            return
        backend = self._get_backend()
        pairs: list[tuple[str, str]] = []
        owner: list[str] = []
        for claim in todo:
            for ch in chunks:
                pairs.append((ch, claim))
                owner.append(claim)
        best: dict[str, float] = {c: 0.0 for c in todo}
        bs = self.cfg.batch_size
        for i in range(0, len(pairs), bs):
            probs = backend.predict(pairs[i:i + bs], self.cfg.max_length)
            for claim, p in zip(owner[i:i + bs], probs):
                if p > best[claim]:
                    best[claim] = p
        for claim, score in best.items():
            self._score_cache[(claim, ctx_h)] = round(score, 4)

    def entail_pairs(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        """Entailment probability for arbitrary (premise, hypothesis) pairs, batched.

        The primitive for retrieve-then-verify: score (candidate_chunk, claim) pairs — including
        pairs from *different* claims in one batch, so a rank-parallel short-circuit stays efficient."""
        if not pairs:
            return []
        backend = self._get_backend()
        out: list[float] = []
        bs = self.cfg.batch_size
        for i in range(0, len(pairs), bs):
            out.extend(backend.predict(list(pairs[i:i + bs]), self.cfg.max_length))
        return out

    def score(self, claim: str, context: str) -> float:
        """Graded entailment of ``claim`` by the best-supporting chunk of ``context`` (0..1)."""
        if not claim.strip() or not (context or "").strip():
            return 0.0
        ctx_h = _hash(context)
        cached = self._score_cache.get((claim, ctx_h))
        if cached is not None:
            return cached
        chunks = self._chunks_for(context)
        backend = self._get_backend()
        best = 0.0
        bs = self.cfg.batch_size
        pairs = [(ch, claim) for ch in chunks]
        for i in range(0, len(pairs), bs):
            best = max([best, *backend.predict(pairs[i:i + bs], self.cfg.max_length)])
        self._score_cache[(claim, ctx_h)] = round(best, 4)
        return self._score_cache[(claim, ctx_h)]


# process-wide singletons keyed by config so the weights load once
_INSTANCES: dict[NliConfig, LocalNli] = {}
_INSTANCES_LOCK = threading.Lock()


def get_local_nli(cfg: Optional[NliConfig] = None) -> LocalNli:
    cfg = cfg or NliConfig()
    with _INSTANCES_LOCK:
        if cfg not in _INSTANCES:
            _INSTANCES[cfg] = LocalNli(cfg)
        return _INSTANCES[cfg]


def grounding_scorer(cfg: Optional[NliConfig] = None):
    """Return an async ``(claim, response, context) -> float`` grounding scorer (the injection seam).

    Model inference runs in a threadpool so it doesn't block the event loop. Pair with
    :meth:`LocalNli.warm` (via ``prewarm``) for batched speed."""
    nli = get_local_nli(cfg)

    async def grounded(claim: str, response: str, context: str) -> float:
        return await asyncio.to_thread(nli.score, claim, context)

    return grounded


async def prewarm(claims: Sequence[str], context: str, cfg: Optional[NliConfig] = None) -> None:
    """Batched pre-scoring of all claims against the context (fills the cache) in a threadpool."""
    nli = get_local_nli(cfg)
    await asyncio.to_thread(nli.warm, list(claims), context)
