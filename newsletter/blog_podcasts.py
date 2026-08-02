import html
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from .cost import CostTracker
from .llm import LLMClient
from .summarize import summarize_items
from .urls import canonical_key

_UA = "Mozilla/5.0 (compatible; research-newsletter-pipeline/1.0)"
_TIMEOUT = 15

_TAG_RE = re.compile(r"<[^>]+>")

# A feed's own content/summary field below this many characters is a teaser, not
# real content — better to leave `text` empty and let summarize_items' existing
# scrape-the-URL fallback hit the live page instead of summarizing a stub.
_MIN_FEED_TEXT_CHARS = 300

# Exact string prompts/blog-podcast-summary.md asks for when an entry (a vacation
# notice, a newsletter-signup teaser, a stub) has nothing substantive to report, so
# it drops cleanly instead of producing a summary that describes its own confusion.
_NOTHING = "NOTHING TO SUMMARIZE"


def _fetch(url: str) -> requests.Response | None:
    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    except Exception:
        return None
    return resp if resp.ok else None


def _resolve_feed(name: str, url: str) -> feedparser.FeedParserDict | None:
    """Fetch and parse `url` as an RSS/Atom feed directly — no autodiscovery, no
    scraping. `url` in config must already be a feed URL. Returns None (after
    printing one named warning) if the fetch fails or it doesn't parse as a feed
    with entries."""
    resp = _fetch(url)
    if resp is None:
        print(f"  [blog_podcasts] {name}: fetch failed for {url}")
        return None

    parsed = feedparser.parse(resp.content)
    if parsed.entries:
        return parsed

    print(f"  [blog_podcasts] {name}: {url} did not parse as an RSS/Atom feed")
    return None


def _entry_datetime(entry) -> datetime | None:
    struct = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime(*struct[:6], tzinfo=timezone.utc) if struct else None


def _strip_html(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", raw or ""))).strip()


def _entry_text(entry) -> str:
    content = entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""
    summary = entry.get("summary", "")
    candidate = content if len(content) > len(summary) else summary
    stripped = _strip_html(candidate)
    return stripped if len(stripped) >= _MIN_FEED_TEXT_CHARS else ""


def run_blog_podcasts(
    sources: list[dict],
    recency_days: int,
    num_results: int = 5,
    summarize_llm: LLMClient | None = None,
    summarize_model: str | None = None,
    tracker: CostTracker | None = None,
) -> list[dict]:
    """One entry per recent blog post / podcast episode, across all configured
    sources, deduped and capped per source.

    Returns [{"url", "title", "summary", "published_date", "source_domain",
    "source_name"}].
    """
    if not sources:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=recency_days)
    seen_keys: set[str] = set()
    dupes = 0
    undated = 0
    skipped_sources = 0
    items: list[dict] = []

    print(f"[blog_podcasts] Checking {len(sources)} source(s) "
          f"(recency: {recency_days}d, {num_results} results each):")

    for source in sources:
        name, url = source["name"], source["url"]
        parsed = _resolve_feed(name, url)
        if parsed is None:
            skipped_sources += 1
            continue

        kept = []
        for entry in parsed.entries:
            dt = _entry_datetime(entry)
            if dt is None:
                undated += 1
                continue
            if dt < cutoff:
                continue

            link = entry.get("link", "")
            if not link:
                continue
            key = canonical_key(link)
            if key in seen_keys:
                dupes += 1
                continue
            seen_keys.add(key)

            kept.append({
                "url": link,
                "title": entry.get("title", ""),
                "published_date": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_domain": link.split("/")[2] if "/" in link else "",
                "source_name": name,
                "text": _entry_text(entry),
                "_sort_dt": dt,
            })

        kept.sort(key=lambda i: i["_sort_dt"], reverse=True)
        kept = kept[:num_results]
        for i in kept:
            i.pop("_sort_dt")
        items.extend(kept)
        print(f"  [blog_podcasts] {name}: {len(kept)} item(s) in window "
              f"(of {len(parsed.entries)} in feed)")

    print(
        f"[blog_podcasts] {len(items)} unique item(s) found across "
        f"{len(sources) - skipped_sources}/{len(sources)} source(s)"
        + (f" ({dupes} duplicates merged)" if dupes else "")
        + (f" ({undated} undated entries skipped)" if undated else "")
        + (f" ({skipped_sources} source(s) skipped — no feed found)" if skipped_sources else "")
    )

    if not items:
        return []

    items, _stats = summarize_items(
        items, summarize_llm, summarize_model, tracker,
        label="blog_podcasts", prompt_name="blog-podcast-summary",
    )

    kept = [i for i in items if _NOTHING not in i["summary"].upper()]
    dropped = len(items) - len(kept)
    if dropped:
        print(f"[blog_podcasts] {dropped} item(s) dropped — nothing to summarize")
    return kept
