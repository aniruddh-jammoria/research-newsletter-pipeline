import json
import os
from datetime import datetime, timedelta, timezone

from exa_py import Exa
from exa_py.api import ContentsOptions, SummaryContentsOptions

from .cost import CostTracker
from .llm import LLMClient
from .prompts import load, load_memory, with_memory



def _cutoff_date(recency_days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=recency_days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Step 1: Exa search ────────────────────────────────────────────────────────

def search_exa(queries: list[str], recency_days: int, num_results: int = 10) -> list[dict]:
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        raise EnvironmentError("EXA_API_KEY not set")

    exa = Exa(api_key=api_key)
    cutoff = _cutoff_date(recency_days)
    seen_urls: set[str] = set()
    articles: list[dict] = []

    for query in queries:
        try:
            response = exa.search(
                query,
                num_results=num_results,
                start_published_date=cutoff,
                category="news",
                contents=ContentsOptions(
                    summary=SummaryContentsOptions(query=query),
                ),
            )
        except Exception as e:
            print(f"  [search] skipping query '{query}': {e}")
            continue

        for r in response.results:
            url = r.url
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            summary = getattr(r, "summary", "") or ""
            articles.append({
                "url": url,
                "title": r.title or "",
                "published_date": r.published_date or "",
                "source_domain": url.split("/")[2] if "/" in url else "",
                "summary": summary,
            })

    return articles


# ── Step 2: Newsworthiness filter ─────────────────────────────────────────────

def filter_newsworthiness(
    articles: list[dict],
    search_queries: list[str],
    llm: LLMClient,
    fast_model: str,
    tracker: CostTracker,
) -> list[dict]:
    if not articles:
        return []

    memory = load_memory()
    system = with_memory(load("newsworthiness"), memory)

    query_list = "\n".join(f"- {q}" for q in search_queries)
    candidates = [
        {
            "url": a["url"],
            "title": a["title"],
            "published_date": a["published_date"],
            "summary": a["summary"],
        }
        for a in articles
    ]

    user_msg = (
        f"Search queries used to find these articles:\n{query_list}\n\n"
        f"Filter the following {len(candidates)} articles. "
        f"Keep every article that meets the newsworthiness criteria — do not limit the count.\n\n"
        f"Articles:\n{json.dumps(candidates, indent=2)}"
    )

    text, inp, out = llm.complete(fast_model, system, user_msg, max_tokens=8192)
    tracker.add(fast_model, inp, out)

    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    result = json.loads(raw)
    keep_urls = {item["url"] for item in result.get("keep", [])}
    drop_count = len(result.get("drop", []))
    print(f"[research] Filter: {len(keep_urls)} kept, {drop_count} dropped")

    return [a for a in articles if a["url"] in keep_urls]


# ── Public entry point ────────────────────────────────────────────────────────

def run_research(
    search_queries: list[str],
    recency_days: int,
    num_results: int,
    llm: LLMClient,
    fast_model: str,
    tracker: CostTracker,
) -> list[dict]:
    print(f"[research] Running {len(search_queries)} search queries (recency: {recency_days}d, {num_results} results each):")
    for i, q in enumerate(search_queries, 1):
        print(f"  {i:2}. {q}")

    articles = search_exa(search_queries, recency_days, num_results)
    print(f"[research] {len(articles)} unique articles found")

    if not articles:
        print("[research] No articles found — check your API key and query terms")
        return []

    print(f"[research] Filtering for newsworthiness...")
    kept = filter_newsworthiness(articles, search_queries, llm, fast_model, tracker)
    print(f"[research] {len(kept)} articles kept after filter")

    return kept
