import os
from datetime import datetime, timedelta, timezone

from exa_py import Exa
from exa_py.api import ContentsOptions, TextContentsOptions

from .cost import CostTracker
from .llm import LLMClient
from .summarize import summarize_items
from .urls import canonical_key, display_url

_TEXT_CHARS = 8000  # see research.py — text is bundled, Exa's own summary is not


def _cutoff_date(recency_days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=recency_days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_papers(
    queries: list[str],
    sources: list[str],
    recency_days: int,
    num_results: int = 5,
    summarize_llm: LLMClient | None = None,
    summarize_model: str | None = None,
    tracker: CostTracker | None = None,
) -> list[dict]:
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        raise EnvironmentError("EXA_API_KEY not set")

    if not queries or not sources:
        return []

    exa = Exa(api_key=api_key)
    cutoff = _cutoff_date(recency_days)
    seen_keys: set[str] = set()
    dupes = 0
    papers: list[dict] = []

    print(f"[papers] Searching {len(queries)} quer(ies) on {sources} (recency: {recency_days}d, {num_results} results each):")
    for query in queries:
        print(f"  · {query}")
        try:
            response = exa.search(
                query,
                num_results=num_results,
                start_published_date=cutoff,
                include_domains=sources,
                contents=ContentsOptions(
                    text=TextContentsOptions(max_characters=_TEXT_CHARS),
                ),
            )
        except Exception as e:
            print(f"  [papers] skipping query '{query}': {e}")
            continue

        for r in response.results:
            url = r.url
            if not url:
                continue
            # arXiv serves one paper at /abs/, /html/ and /pdf/, so identity has
            # to be the paper, not the URL string.
            key = canonical_key(url)
            if key in seen_keys:
                dupes += 1
                continue
            seen_keys.add(key)

            url = display_url(url)
            papers.append({
                "url": url,
                "title": r.title or "",
                "published_date": r.published_date or "",
                "source_domain": url.split("/")[2] if "/" in url else "",
                "text": getattr(r, "text", "") or "",
            })

    print(f"[papers] {len(papers)} unique papers found"
          + (f" ({dupes} same-document duplicates merged)" if dupes else ""))

    if not papers:
        return []

    papers, _stats = summarize_items(papers, summarize_llm, summarize_model, tracker, label="papers")
    return papers
