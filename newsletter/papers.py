import os
from datetime import datetime, timedelta, timezone

from exa_py import Exa
from exa_py.api import ContentsOptions, SummaryContentsOptions


def _cutoff_date(recency_days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=recency_days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_papers(
    queries: list[str],
    sources: list[str],
    recency_days: int,
    num_results: int = 5,
) -> list[dict]:
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        raise EnvironmentError("EXA_API_KEY not set")

    if not queries or not sources:
        return []

    exa = Exa(api_key=api_key)
    cutoff = _cutoff_date(recency_days)
    seen_urls: set[str] = set()
    papers: list[dict] = []

    print(f"[papers] Searching {len(queries)} quer(ies) on {sources} (recency: {recency_days}d):")
    for query in queries:
        print(f"  · {query}")
        try:
            response = exa.search(
                query,
                num_results=num_results,
                start_published_date=cutoff,
                include_domains=sources,
                contents=ContentsOptions(
                    summary=SummaryContentsOptions(query=query),
                ),
            )
        except Exception as e:
            print(f"  [papers] skipping query '{query}': {e}")
            continue

        for r in response.results:
            url = r.url
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            summary = getattr(r, "summary", "") or ""
            papers.append({
                "url": url,
                "title": r.title or "",
                "published_date": r.published_date or "",
                "source_domain": url.split("/")[2] if "/" in url else "",
                "summary": summary,
            })

    print(f"[papers] {len(papers)} unique papers found")
    return papers
