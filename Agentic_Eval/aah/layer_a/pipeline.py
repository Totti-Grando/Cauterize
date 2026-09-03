"""Layer A standalone runtime (spec §5). Question in -> AuditRecord out.

The §5 fork: once the question exists, concurrently (a) query the provider and (b) generate
the rubric; join on the response; route every rubric question to a verdict; aggregate via the
§7 mapping; emit an AuditRecord. Standalone stops here -- the loop (Layer B) wraps this.

M0 ships the wiring with stub modules so the skeleton runs end-to-end. M1 swaps in real
implementations behind the same interfaces; M2 inserts the §9 guard (prune -> kept_question_ids).
"""

from __future__ import annotations

import asyncio
from typing import Optional

from ..config import default_weight_config
from ..contracts import AgentInfo, AuditRecord, Mode, Provenance, RunScore, Tier, Verdict, WeightConfig
from ..model_families import same_family
from ..determinism_guards import combine_runs, kept_after_phi_dedup
from .aggregator import aggregate, effective_weights_of, focus_profile
from .providers.base import ProviderAdapter
from .question_gen import QuestionGenerator
from .router import EvaluatorRouter
from .rubric_gen import RubricGenerator


async def run_once(
    *,
    seed: str,
    p_q: str,
    mode: Mode,
    generator: QuestionGenerator,
    provider: ProviderAdapter,
    rubric_gen: RubricGenerator,
    router: EvaluatorRouter,
    config: Optional[WeightConfig] = None,
    context: Optional[str] = None,
    prompt_version: str = "P_Q@v0",
    iteration: int = 0,
    kept_question_ids: Optional[set[str]] = None,
    runs: int = 1,
    evaluator: Optional[AgentInfo] = None,
    provider_info: Optional[AgentInfo] = None,
    gating_router: Optional[EvaluatorRouter] = None,
    gating_panel: Optional[list[EvaluatorRouter]] = None,
) -> AuditRecord:
    """Execute one Layer A pass and return its AuditRecord (not yet persisted).

    With ``runs > 1`` the provider is queried and scored that many times and the verdicts
    are combined via the §9 2-run averaging guard, so borderline questions that flip between
    0 and 1 are resolved conservatively rather than scored at random. The first response is
    kept as the representative response on the AuditRecord.
    """

    if runs < 1:
        raise ValueError("runs must be >= 1")
    config = config or default_weight_config()

    # Step 2: generate the question.
    question = generator.generate(p_q, seed, mode)
    ctx = context if context is not None else seed

    # Step 3-4: fork (rubric build || all provider queries), join.
    rubric_task = asyncio.to_thread(rubric_gen.build, question, ctx)
    response_tasks = [provider.query(question) for _ in range(runs)]
    rubric, *responses = await asyncio.gather(rubric_task, *response_tasks)

    # F5: if the rubric carries any gating (CRITICAL) check, top up to gating_min_runs so a
    # single noisy verdict can't decide a hard FAIL — conservative-to-fail averaging damps it.
    has_gating = any(config.tiers.get(q.dimension) is Tier.CRITICAL for q in rubric)
    need = max(1, config.gating_min_runs) if has_gating else 1
    while len(responses) < need:
        responses.append(await provider.query(question))

    # Step 5: route each question to a verdict, once per run; combine across runs (§9).
    # F4: CRITICAL gating checks may be scored by a cross-family REFERENCE judge (to avoid
    # self-enhancement bias) and/or by a PANEL that fails the gate if ANY panelist fails.
    async def _score(q, resp):
        is_gating = config.tiers.get(q.dimension) is Tier.CRITICAL
        if is_gating and gating_panel:
            votes = list(await asyncio.gather(*(r.score(q, resp, ctx) for r in gating_panel)))
            return min(votes, key=lambda v: v.score)  # fail-closed: any failing panelist fails
        chosen = gating_router if (is_gating and gating_router is not None) else router
        return await chosen.score(q, resp, ctx)

    per_run: list[list[Verdict]] = [
        list(await asyncio.gather(*(_score(q, resp) for q in rubric)))
        for resp in responses
    ]
    verdicts: list[Verdict] = per_run[0] if len(per_run) == 1 else combine_runs(per_run)
    response = responses[0]

    # F8: phi-dedup redundant checks within a dimension BEFORE the uniform average, so
    # near-duplicate checks don't double-weight one facet. Needs >=2 samples with variance;
    # with a single run nothing is dropped. An explicit ``kept_question_ids`` overrides this.
    kept = kept_question_ids
    if kept is None and len(per_run) >= 2:
        scores_by_id: dict[str, list[int]] = {}
        for run in per_run:
            for v in run:
                scores_by_id.setdefault(v.question_id, []).append(v.score)
        kept = kept_after_phi_dedup(
            {q.id: q.dimension for q in rubric}, scores_by_id,
            phi_threshold=config.prune_thresholds.phi,
        )

    # Step 6: aggregate via the deterministic §7 mapping.
    scores: RunScore = aggregate(verdicts, rubric, config, kept)

    # Step 6b: provenance (F1) — record WHO judged and WHO was judged. Infer non-empty ids from
    # the components when the caller didn't pass resolved runtime info, so no record is emitted
    # with a null evaluator/provider model.
    prov = provider_info or AgentInfo(
        backend=getattr(provider, "name", "") or "provider",
        model=getattr(provider, "name", "") or "provider",
    )
    evalr = evaluator or AgentInfo(
        backend="stub" if type(generator).__name__.startswith("Stub") else "claude",
        model=getattr(generator, "_model", "") or type(generator).__name__,
    )
    provenance = Provenance(
        evaluator=evalr,
        provider=prov,
        same_family_judge=same_family(evalr.backend, evalr.model, prov.backend, prov.model),
    )

    # Step 6c: per-dimension yes-rate summary (F6) for leniency monitoring.
    yes_rate_summary = _yes_rate_by_dimension(rubric, verdicts)

    # Step 7: emit the AuditRecord (R7: stamp the focus profile + effective weights).
    return AuditRecord(
        mode=mode,
        task=seed,
        question=question,
        response=response,
        rubric=rubric,
        verdicts=verdicts,
        scores=scores,
        weight_config=config,
        prompt_version=prompt_version,
        iteration=iteration,
        provenance=provenance,
        yes_rate_summary=yes_rate_summary,
        focus=focus_profile(config),
        effective_weights=effective_weights_of(scores),
    )


def _yes_rate_by_dimension(rubric, verdicts) -> dict[str, float]:
    """Mean pass-rate per dimension — surfaced for the F6 leniency/yes-bias monitor."""
    dim_by_q = {q.id: q.dimension for q in rubric}
    buckets: dict[str, list[int]] = {}
    for v in verdicts:
        dim = dim_by_q.get(v.question_id)
        if dim is None:
            continue
        buckets.setdefault(dim.value, []).append(v.score)
    return {d: (sum(s) / len(s)) for d, s in buckets.items() if s}
