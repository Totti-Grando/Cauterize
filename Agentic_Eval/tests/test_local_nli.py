"""Tests for the local-NLI handler's logic (aah/api/local_nli.py): chunking, max-aggregation,
caching, and batched warm() — all with a FAKE backend so no torch/model download is needed.
"""

from __future__ import annotations

import pytest

from aah.api import local_nli as ln
from aah.api.local_nli import LocalNli, NliConfig, _entailment_index


class _FakeTokenizer:
    """Whitespace tokenizer whose 'ids' are the words themselves, so decode() reconstructs text."""

    def __call__(self, text, text_pair=None, add_special_tokens=True, **k):
        return {"input_ids": (text or "").split()}

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(ids)


class _FakeBackend:
    """Scores a (premise, hypothesis) pair by word-overlap of the hypothesis in the premise."""

    def __init__(self, cfg):
        self.tokenizer = _FakeTokenizer()
        self.calls = 0

    def predict(self, pairs, max_length):
        self.calls += len(pairs)
        out = []
        for premise, hyp in pairs:
            hw = set(hyp.split())
            out.append(len(hw & set(premise.split())) / len(hw) if hw else 0.0)
        return out


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(ln, "_make_backend", lambda cfg: _FakeBackend(cfg))


def test_entailment_index_from_id2label():
    class C:  # noqa: D401
        id2label = {0: "contradiction", 1: "neutral", 2: "entailment"}
    assert _entailment_index(C()) == 2

    class C2:
        id2label = {0: "ENTAILMENT", 1: "NON_ENTAILMENT"}
    assert _entailment_index(C2()) == 0


def test_score_is_max_entailment_over_chunks(patched):
    nli = LocalNli(NliConfig(max_length=160, max_chunks=8))  # window=64 words
    # clean (punctuation-free) so the whitespace fake tokenizer matches words exactly
    ctx = "the revenue was four billion dollars and cloud margin improved this quarter"
    assert nli.score("revenue was four billion", ctx) == pytest.approx(1.0)
    # a claim absent from the context scores low
    assert nli.score("penguins migrate south", ctx) < 0.4


def test_score_is_cached_no_recompute(patched):
    nli = LocalNli(NliConfig())
    ctx = "revenue was four billion dollars this quarter"
    first = nli.score("revenue four billion", ctx)
    calls_after_first = nli._get_backend().calls
    second = nli.score("revenue four billion", ctx)          # identical -> cache hit
    assert second == first
    assert nli._get_backend().calls == calls_after_first     # no additional predict calls


def test_warm_batches_and_fills_cache(patched):
    nli = LocalNli(NliConfig(batch_size=4))
    ctx = "revenue was four billion cloud margin improved to sixty eight percent"
    claims = ["revenue four billion", "cloud margin sixty eight", "unrelated mascot penguin"]
    nli.warm(claims, ctx)
    backend = nli._get_backend()
    calls_after_warm = backend.calls
    # every claim is now cached -> scoring adds zero predict calls
    for c in claims:
        nli.score(c, ctx)
    assert backend.calls == calls_after_warm
    assert nli.score("revenue four billion", ctx) == pytest.approx(1.0)


def test_empty_inputs_score_zero(patched):
    nli = LocalNli(NliConfig())
    assert nli.score("", "some context") == 0.0
    assert nli.score("a claim", "") == 0.0


def test_chunk_cap_is_respected(patched):
    nli = LocalNli(NliConfig(max_length=160, max_chunks=3))   # window 64, cap 3
    long_ctx = " ".join(f"word{i}" for i in range(1000))
    chunks = nli._chunks_for(long_ctx)
    assert len(chunks) == 3
