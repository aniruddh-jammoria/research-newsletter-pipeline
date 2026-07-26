"""The "This Week's Overview" block at the top of the newsletter.

One extra LLM call, made after the newsworthiness filter so it only ever sees
articles that actually made the newsletter. Kept separate from the filter and
summarize passes because it is a synthesis over the whole selection rather than
a judgement about any single article.
"""
import json
import re

from .cost import CostTracker
from .llm import LLMClient
from .prompts import load

MAX_BULLETS = 5

# Reasoning models spend hidden tokens from the same budget as the answer, so
# this needs the same headroom summarize.py uses.
_MAX_TOKENS = 2560

# Each summary is already 100-150 words; this only guards against an outlier.
_MAX_SUMMARY_CHARS = 900

_BULLET_LINE = re.compile(r"^(?:[-*•‣◦]|\d+[.)])\s+(.*)$")


def _parse(raw: str) -> list[str]:
    """Prefer a JSON array; fall back to markdown-style bullets.

    The prompt asks for JSON, but a local model that has just spent its
    reasoning budget sometimes answers with a plain bullet list instead. That is
    a perfectly usable answer, so it is worth reading rather than discarding.
    """
    text = (raw or "").strip()

    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1]
            if text.lower().startswith("json"):
                text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except json.JSONDecodeError:
        pass

    return [
        m.group(1).strip()
        for m in (_BULLET_LINE.match(line.strip()) for line in text.splitlines())
        if m and m.group(1).strip()
    ]


def generate(
    articles: list[dict],
    llm: LLMClient,
    model: str,
    tracker: CostTracker,
) -> list[str]:
    """Return up to MAX_BULLETS overview bullets for `articles`.

    Returns an empty list on any failure. The overview is an addition to a
    newsletter that is already complete, so it must never take down a run —
    the template simply omits the section when there is nothing to show.
    """
    if not articles:
        return []

    system = load("overview")
    items = [
        {
            "title":   a.get("title", ""),
            "source":  a.get("source_domain", ""),
            "summary": (a.get("summary") or "")[:_MAX_SUMMARY_CHARS],
        }
        for a in articles
    ]
    user = (
        f"Here are the {len(items)} news articles selected for this week's newsletter.\n"
        f"Write the overview as instructed, with at most {MAX_BULLETS} bullet points.\n\n"
        f"{json.dumps(items, indent=2)}"
    )

    print(f"[overview] Generating from {len(items)} articles via {llm.provider} ({model})...")
    try:
        text, inp, out = llm.complete(model, system, user, max_tokens=_MAX_TOKENS)
        tracker.add(model, inp, out)
    except Exception as e:
        print(f"[overview] failed, continuing without an overview: {e}")
        return []

    bullets = _parse(text)[:MAX_BULLETS]
    if not bullets:
        print("[overview] no usable bullets returned, continuing without an overview")
        return []

    print(f"[overview] {len(bullets)} bullet(s) written")
    return bullets
