"""Capture scorers, one per ``EvalMethod`` (spec §5 step 5, §6).

The router (:mod:`aah.layer_a.router`) maps ``question.eval_method`` to the matching scorer
here. Every scorer returns a :class:`~aah.contracts.Verdict` with a mandatory explanation.
"""

from .base import Scorer
from .deterministic import DeterministicScorer
from .fabrication import FabricationScorer
from .injection import InjectionDetectorScorer
from .llm_judge import ClaudeJudgeScorer
from .nli import ClaudeNLIScorer, HttpNLIScorer, LocalNLIScorer, make_nli
from .source_fetch import SourceFetchScorer

__all__ = [
    "Scorer",
    "DeterministicScorer",
    "FabricationScorer",
    "ClaudeNLIScorer",
    "HttpNLIScorer",
    "LocalNLIScorer",
    "make_nli",
    "SourceFetchScorer",
    "ClaudeJudgeScorer",
    "InjectionDetectorScorer",
]
