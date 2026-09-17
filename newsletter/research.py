import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from exa_py import Exa
from exa_py.api import ContentsOptions, TextContentsOptions

from .cost import CostTracker
from .exa_cache import get_or_fetch
from .llm import LLMClient
from .prompts import load, load_memory, with_memory
from .summarize import summarize_items
from .urls import canonical_key

_LOGS_DIR = Path(__file__).parent.parent / "logs"
_MAX_TOKENS = 8192  # output cap for keep/drop passes — response is a short array, this is headroom

# Page text is bundled into the base search price for the first 10 results,
# whereas Exa's generated summary is a separate per-page charge. We ask for text
# and write our own summary, which is both cheaper and gives every downstream
# stage a neutral summary rather than one angled at whichever query matched.
_TEXT_CHARS = 8000  # cap at the source; summarize.py trims further before the LLM


def _cutoff_date(recency_days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=recency_days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_run_log(run_id: str, log: dict) -> None:
    _LOGS_DIR.mkdir(exist_ok=True)
    path = _LOGS_DIR / f"{run_id}.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    existing.update(log)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"[research] Log written to {path}")


# ── Step 1: Exa search ────────────────────────────────────────────────────────

def search_exa(queries: list[str], recency_days: int, num_results: int = 5) -> tuple[list[dict], int]:
    """Returns (articles, number of same-document duplicates merged)."""

    def _fetch() -> dict:
        api_key = os.getenv("EXA_API_KEY")
        if not api_key:
            raise EnvironmentError("EXA_API_KEY not set")

        exa = Exa(api_key=api_key)
        cutoff = _cutoff_date(recency_days)
        seen_keys: set[str] = set()
        dupes = 0
        articles: list[dict] = []

        for query in queries:
            try:
                response = exa.search(
                    query,
                    num_results=num_results,
                    start_published_date=cutoff,
                    category="news",
                    contents=ContentsOptions(
                        text=TextContentsOptions(max_characters=_TEXT_CHARS),
                    ),
                )
            except Exception as e:
                print(f"  [search] skipping query '{query}': {e}")
                continue

            for r in response.results:
                url = r.url
                if not url:
                    continue
                # Same page under a different tracking param or www/https form is
                # the same article. Genuine duplicate *coverage* is the LLM pass's
                # job; this only catches identical documents.
                key = canonical_key(url)
                if key in seen_keys:
                    dupes += 1
                    continue
                seen_keys.add(key)

                articles.append({
                    "url": url,
                    "title": r.title or "",
                    "published_date": r.published_date or "",
                    "source_domain": url.split("/")[2] if "/" in url else "",
                    "text": getattr(r, "text", "") or "",
                })

        return {"articles": articles, "dupes": dupes}

    result = get_or_fetch(
        "news", {"queries": queries, "recency_days": recency_days, "num_results": num_results}, _fetch
    )
    return result["articles"], result["dupes"]


# ── Shared keep/drop pass ─────────────────────────────────────────────────────

def _keep_drop_pass(
    articles: list[dict],
    system: str,
    user_msg: str,
    llm: LLMClient,
    model: str,
    tracker: CostTracker,
    step_label: str,
) -> tuple[list[dict], dict]:
    """Run one LLM keep/drop pass over `articles`. Returns (kept_articles, log_dict)."""
    n = len(articles)

    text, inp, out = llm.complete(model, system, user_msg, max_tokens=_MAX_TOKENS)
    tracker.add(model, inp, out)
    first_attempt_text = None

    def _parse(raw: str) -> list:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    def _validate(decisions) -> list:
        if not isinstance(decisions, list) or len(decisions) != n:
            got = len(decisions) if isinstance(decisions, list) else type(decisions).__name__
            raise ValueError(f"expected a list of exactly {n} decisions, got {got}")
        return decisions

    try:
        decisions = _validate(_parse(text))
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[research] {step_label} response invalid ({e}), retrying with fix request...")
        first_attempt_text = text
        fix_msg = (
            f"The following output is invalid. It must be a JSON array of exactly "
            f"{n} strings (\"keep\" or \"drop\"), nothing else. "
            f"Fix and return only the corrected array:\n\n{text}"
        )
        text2, inp2, out2 = llm.complete(model, system, fix_msg, max_tokens=_MAX_TOKENS)
        tracker.add(model, inp2, out2)
        parsed2 = _parse(text2)
        if isinstance(parsed2, list) and len(parsed2) > n:
            print(f"[research] {step_label} retry still returned {len(parsed2)} decisions, truncating to {n}")
            parsed2 = parsed2[:n]
        decisions = _validate(parsed2)
        text = text2

    kept = [a for a, d in zip(articles, decisions) if str(d).strip().lower() == "keep"]
    drop_count = n - len(kept)
    print(f"[research] {step_label}: {len(kept)} kept, {drop_count} dropped")

    log = {
        "candidates": [{"url": a["url"], "title": a["title"]} for a in articles],
        "llm_raw_output": text,
        "llm_decisions": decisions,
    }
    if first_attempt_text is not None:
        log["llm_raw_output_first_attempt_invalid"] = first_attempt_text

    return kept, log


# ── Step 2: Deduplication ──────────────────────────────────────────────────────

def deduplicate_articles(
    articles: list[dict],
    filter_llm: LLMClient,
    filter_model: str,
    tracker: CostTracker,
    run_id: str | None = None,
) -> list[dict]:
    if not articles:
        return []

    memory = load_memory()
    system = with_memory(load("deduplication"), memory)

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
        f"Decide keep or drop for each of the following {len(candidates)} articles.\n"
        f"Respond with a JSON array of exactly {len(candidates)} strings — \"keep\" or \"drop\" — "
        f"one per article, in the exact same order as the articles below. Do not repeat URLs, "
        f"titles, or anything else — only the array.\n\n"
        f"Articles:\n{json.dumps(candidates, indent=2)}"
    )

    kept, log = _keep_drop_pass(articles, system, user_msg, filter_llm, filter_model, tracker, "Dedup")

    if run_id is not None:
        _write_run_log(run_id, {"dedup": log})

    return kept


# ── Step 3: Newsworthiness filter ─────────────────────────────────────────────

def filter_newsworthiness(
    articles: list[dict],
    search_queries: list[str],
    filter_llm: LLMClient,
    filter_model: str,
    tracker: CostTracker,
    run_id: str | None = None,
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
        f"Decide keep or drop for each of the following {len(candidates)} articles.\n"
        f"Respond with a JSON array of exactly {len(candidates)} strings — \"keep\" or \"drop\" — "
        f"one per article, in the exact same order as the articles below. Do not repeat URLs, "
        f"titles, or anything else — only the array.\n\n"
        f"Articles:\n{json.dumps(candidates, indent=2)}"
    )

    kept, log = _keep_drop_pass(articles, system, user_msg, filter_llm, filter_model, tracker, "Filter")

    if run_id is not None:
        log["search_queries"] = search_queries
        _write_run_log(run_id, {"filter": log})

    return kept


# ── Public entry point ────────────────────────────────────────────────────────

def run_research(
    search_queries: list[str],
    recency_days: int,
    num_results: int,
    filter_llm: LLMClient,
    filter_model: str,
    tracker: CostTracker,
    summarize_llm: LLMClient,
    summarize_model: str,
    run_id: str | None = None,
) -> list[dict]:
    print(f"[research] Running {len(search_queries)} search queries (recency: {recency_days}d, {num_results} results each):")
    for i, q in enumerate(search_queries, 1):
        print(f"  {i:2}. {q}")

    articles, dupes = search_exa(search_queries, recency_days, num_results)
    print(f"[research] {len(articles)} unique articles found"
          + (f" ({dupes} same-document duplicates merged)" if dupes else ""))

    if not articles:
        print("[research] No articles found — check your API key and query terms")
        return []

    # Summarize before filtering, not after. Both keep/drop passes then judge a
    # neutral, uniform-length summary written from the article's own text,
    # rather than a search-engine summary angled at whichever query matched.
    # The same summary is what ends up in the newsletter, so this replaces the
    # old post-filter summarization rather than adding a second pass.
    articles, summary_stats = summarize_items(
        articles, summarize_llm, summarize_model, tracker, label="research"
    )
    if run_id is not None:
        _write_run_log(run_id, {"summarize": summary_stats})

    if not articles:
        print("[research] No articles had usable content")
        return []

    print(f"[research] Deduplicating...")
    deduped = deduplicate_articles(articles, filter_llm, filter_model, tracker, run_id=run_id)
    print(f"[research] {len(deduped)} articles remain after dedup")

    print(f"[research] Filtering for newsworthiness...")
    kept = filter_newsworthiness(deduped, search_queries, filter_llm, filter_model, tracker, run_id=run_id)
    print(f"[research] {len(kept)} articles kept after filter")

    return kept
