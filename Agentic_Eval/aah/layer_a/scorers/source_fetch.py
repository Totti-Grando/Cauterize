"""Source-fetch scorer (spec §6: ``source_fetch``).

Pulls a URL out of the ``response`` (or ``context``), fetches + extracts the page text via
trafilatura, then delegates an ``nli`` claim-check of ``question.text`` against that text.
Both the fetcher and the nli scorer are injectable constructor args so unit tests run fully
offline (fake fetcher returns canned text; stub/fake nli).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable, Optional

from ...contracts import BinaryQuestion, Verdict
from .base import Scorer
from .nli import ClaudeNLIScorer

_URL_RE = re.compile(r"https?://[^\s)<>\"']+", re.IGNORECASE)

#: A fetcher takes a URL and returns the extracted page text (empty string on failure).
Fetcher = Callable[[str], str]


def extract_url(text: str) -> Optional[str]:
    """Return the first http(s) URL in ``text``, or ``None``."""
    if not text:
        return None
    match = _URL_RE.search(text)
    return match.group(0) if match else None


class SourceFetchScorer:
    """Open a link, extract its text, and claim-check ``question.text`` against it."""

    def __init__(
        self,
        nli: Optional[Scorer] = None,
        fetcher: Optional[Fetcher] = None,
        client: Any = None,
        model: str = "claude-opus-4-8",
    ):
        self._nli: Scorer = nli or ClaudeNLIScorer(client=client, model=model)
        self._fetcher = fetcher

    def _fetch(self, url: str) -> str:
        """Fetch + extract the page text. Uses trafilatura unless a fetcher was injected."""
        if self._fetcher is not None:
            return self._fetcher(url) or ""
        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        return trafilatura.extract(downloaded) or ""

    async def score(
        self, question: BinaryQuestion, response: str, context: str
    ) -> Verdict:
        url = extract_url(response) or extract_url(context)
        if url is None:
            return Verdict(
                question_id=question.id,
                score=0,
                explanation="no URL found in response or context to fetch",
            )
        # The fetch may block (network / trafilatura) — offload off the event loop.
        page_text = await asyncio.to_thread(self._fetch, url)
        if not page_text:
            return Verdict(
                question_id=question.id,
                score=0,
                explanation=f"could not fetch or extract any text from {url}",
                evidence=url,
            )
        verdict = await self._nli.score(question, response, page_text)
        # Record which source the claim was checked against.
        return verdict.model_copy(update={"evidence": url})
