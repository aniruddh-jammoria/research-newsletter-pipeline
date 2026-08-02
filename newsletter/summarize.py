import re
import time

import trafilatura

from .cost import CostTracker
from .llm import LLMClient
from .prompts import load

_MAX_CHARS = 6000

# The model returns two labelled fields. Labels rather than JSON because a
# malformed label costs only the title — the summary is still usable — whereas a
# malformed JSON object loses both. Tolerates markdown bold and any casing.
_TITLE_RE   = re.compile(r"^[ \t>*_#]*title[ \t*_]*:[ \t]*[*_]*[ \t]*(.+?)[ \t]*$", re.IGNORECASE | re.MULTILINE)
_SUMMARY_RE = re.compile(r"^[ \t>*_#]*summary[ \t*_]*:[ \t]*[*_]*[ \t]*", re.IGNORECASE | re.MULTILINE)

# Beyond this the model has clearly written something other than a title, so the
# original is kept instead.
_MAX_TITLE_CHARS = 250

# Local reasoning models spend hidden "thinking" tokens out of the same budget
# as the visible answer, so a cap sized only for the paragraph can be consumed
# entirely before the model writes anything. Sized for a reasoning budget plus a
# 150-word paragraph. Cloud providers bill on tokens actually produced, so a
# generous cap costs nothing there.
_MAX_TOKENS = 2560

_SCRAPE_TIMEOUT = 15


def _fmt_secs(seconds: float) -> str:
    """m:ss under an hour, h:mm:ss above."""
    seconds = max(int(seconds), 0)
    hours, rem = divmod(seconds, 3600)
    mins, secs = divmod(rem, 60)
    return f"{hours}:{mins:02}:{secs:02}" if hours else f"{mins}:{secs:02}"


def _progress(label, i, total, status, item_secs, started_at, domain) -> None:
    """One line per item. Summarizing is the slowest stage of a local run, so
    this reports after every item rather than in batches — otherwise a run can
    sit silent for minutes and look hung."""
    avg = (time.time() - started_at) / i
    eta = avg * (total - i)
    print(
        f"  [{label}] {i:>3}/{total}  {status:<22} {item_secs:5.1f}s  "
        f"eta {_fmt_secs(eta):>7}  {domain[:30]}",
        flush=True,
    )


def _clean_title(raw: str) -> str:
    """Normalize a model-returned title, or return "" if it is unusable."""
    title = " ".join((raw or "").split())
    title = title.strip("*_# ").strip()
    if len(title) >= 2 and title[0] in "\"'“‘" and title[-1] in "\"'”’":
        title = title[1:-1].strip()
    return "" if len(title) > _MAX_TITLE_CHARS else title


def _parse_response(raw: str, fallback_title: str) -> tuple[str, str]:
    """Split the model's reply into (title, summary).

    Degrades in stages: a missing SUMMARY label still yields the text after the
    title line, and a missing TITLE label still yields the whole reply as the
    summary with the original title kept. The worst case is exactly the
    behaviour before titles were extracted at all.
    """
    text = (raw or "").strip()

    title_match = _TITLE_RE.search(text)
    title = _clean_title(title_match.group(1)) if title_match else ""
    if not title:
        title = fallback_title

    summary_match = _SUMMARY_RE.search(text)
    if summary_match:
        summary = text[summary_match.end():]
    elif title_match:
        summary = text[title_match.end():]
    else:
        summary = text

    return title, summary.strip()


def _scrape(url: str) -> str:
    """Fallback content fetch for pages Exa returned no text for."""
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception:
        return ""
    if not downloaded:
        return ""
    return (trafilatura.extract(downloaded) or "").strip()


def summarize_items(
    items: list[dict],
    llm: LLMClient,
    model: str,
    tracker: CostTracker,
    label: str = "summarize",
    prompt_name: str = "summarize",
) -> tuple[list[dict], dict]:
    """Turn each item's raw page `text` into a model-written summary.

    Content comes from the page text Exa already bundles with the search. When
    Exa returns nothing for a page, the URL is scraped directly as a fallback.

    Items where both fail are dropped rather than carried forward with an empty
    summary: they cannot be judged, cannot be printed, and — because this runs
    before deduplication — several blank summaries in one batch look like
    duplicates of each other. The count is reported and logged instead.

    Returns (items_with_summaries, stats).
    """
    prompt = load(prompt_name)
    total = len(items)
    stats = {"total": total, "exa_text": 0, "scraped": 0, "no_content": 0,
             "llm_failed": 0, "title_rewritten": 0}
    kept: list[dict] = []

    print(f"[{label}] Summarizing {total} items via {llm.provider} ({model})...", flush=True)
    started_at = time.time()

    for i, item in enumerate(items, 1):
        t_item = time.time()
        domain = item.get("source_domain") or ""
        scraped = False

        text = (item.get("text") or "").strip()
        if text:
            stats["exa_text"] += 1
        else:
            text = _scrape(item["url"])
            if text:
                scraped = True
                stats["scraped"] += 1
            else:
                stats["no_content"] += 1
                _progress(label, i, total, "dropped: no content",
                          time.time() - t_item, started_at, domain)
                continue

        original_title = item.get("title", "")
        try:
            raw, inp, out = llm.complete(
                model, prompt, text[:_MAX_CHARS], max_tokens=_MAX_TOKENS
            )
            tracker.add(model, inp, out)
        except Exception as e:
            stats["llm_failed"] += 1
            _progress(label, i, total, "dropped: LLM error",
                      time.time() - t_item, started_at, domain)
            print(f"      -> {item['url']}: {e}")
            continue

        title, summary = _parse_response(raw, original_title)
        if not summary:
            stats["llm_failed"] += 1
            _progress(label, i, total, "dropped: empty summary",
                      time.time() - t_item, started_at, domain)
            continue

        if title != original_title:
            stats["title_rewritten"] += 1

        item["title"] = title
        item["summary"] = summary
        item.pop("text", None)
        kept.append(item)

        words = len(summary.split())
        _progress(label, i, total, f"{words}w{' (scraped)' if scraped else ''}",
                  time.time() - t_item, started_at, domain)

    missing_pct = (stats["no_content"] / total * 100) if total else 0.0
    elapsed = time.time() - started_at
    stats["no_content_pct"] = round(missing_pct, 1)
    stats["elapsed_secs"] = round(elapsed, 1)

    print(
        f"[{label}] {total} in / {len(kept)} summarized in {_fmt_secs(elapsed)} "
        f"({elapsed / total:.1f}s each) — "
        f"Exa text: {stats['exa_text']}, scraped: {stats['scraped']}, "
        f"no content: {stats['no_content']} ({missing_pct:.1f}%), "
        f"titles cleaned: {stats['title_rewritten']}"
        + (f", LLM failures: {stats['llm_failed']}" if stats["llm_failed"] else ""),
        flush=True,
    )

    return kept, stats
