import os
from datetime import datetime, timedelta, timezone

import requests

from .cost import CostTracker
from .llm import LLMClient
from .prompts import load

_BASE = "https://api.getxapi.com"
_DATE_FMT = "%a %b %d %H:%M:%S +0000 %Y"  # "Thu Jun 04 21:19:49 +0000 2026"

# Reasoning models spend hidden tokens from the same budget as the answer.
_MAX_TOKENS = 2560

# A week of posts from one account, bounded so a prolific poster cannot blow up
# the prompt. Well above what any single account produces in practice.
_MAX_CHARS = 12000

# Exact string the prompt asks for when an account posted nothing substantive,
# so quiet weeks drop out instead of producing a padded paragraph.
_NOTHING = "NOTHING NOTABLE"


def _headers() -> dict:
    key = os.getenv("GETXAPI_KEY")
    if not key:
        raise EnvironmentError("GETXAPI_KEY not set")
    return {"Authorization": f"Bearer {key}"}


def _parse_date(created_at: str) -> str:
    try:
        dt = datetime.strptime(created_at, _DATE_FMT).replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


def _fetch_user_tweets(username: str, since: str) -> list[dict]:
    """Every post by `username` since `since`, oldest first.

    No engagement ranking or top-N cut: the whole week is summarized, so
    selecting a subset here would just hide material from the summarizer.
    """
    query = f"from:{username} since:{since} -is:reply"
    try:
        resp = requests.get(
            f"{_BASE}/twitter/tweet/advanced_search",
            headers=_headers(),
            params={"q": query, "product": "Latest"},
            timeout=15,
        )
    except Exception as e:
        print(f"  [twitter] @{username} request error: {e}")
        return []

    if not resp.ok:
        print(f"  [twitter] @{username} failed {resp.status_code}: {resp.text[:150]}")
        return []

    tweets = [
        {
            "text": t.get("text", ""),
            "published_date": _parse_date(t.get("createdAt", "")),
        }
        for t in resp.json().get("tweets", [])
        if (t.get("text") or "").strip()
    ]
    tweets.sort(key=lambda t: t["published_date"])
    return tweets


def _summarize_user(
    username: str,
    tweets: list[dict],
    llm: LLMClient,
    model: str,
    tracker: CostTracker,
) -> str | None:
    """One 50-100 word paragraph for `username`, or None if there is nothing
    worth printing (no substance, or the call failed)."""
    system = load("tweet_summary")

    body, used = [], 0
    for t in tweets:
        line = f"[{t['published_date'][:10]}] {t['text'].strip()}"
        if used + len(line) > _MAX_CHARS:
            break
        body.append(line)
        used += len(line)

    user = (
        f"Posts by this account in the past week ({len(body)} of {len(tweets)}):\n\n"
        + "\n\n".join(body)
    )

    try:
        text, inp, out = llm.complete(model, system, user, max_tokens=_MAX_TOKENS)
        tracker.add(model, inp, out)
    except Exception as e:
        print(f"  [twitter] @{username} summarize failed: {e}")
        return None

    summary = (text or "").strip().strip('"')
    if not summary or _NOTHING.lower() in summary.lower():
        return None
    return summary


def run_twitter(
    usernames: list[str],
    recency_days: int,
    summarize_llm: LLMClient,
    summarize_model: str,
    tracker: CostTracker,
) -> list[dict]:
    """One summary per account, for accounts that posted something substantive.

    Returns [{"username", "summary", "tweet_count", "url"}].
    """
    if not usernames:
        return []

    since = (datetime.now(timezone.utc) - timedelta(days=recency_days)).strftime("%Y-%m-%d")
    print(f"[twitter] Fetching and summarizing {len(usernames)} accounts via getxapi (since {since}):")

    summaries: list[dict] = []
    silent, nothing_notable = 0, 0

    for username in usernames:
        tweets = _fetch_user_tweets(username, since)
        if not tweets:
            silent += 1
            print(f"  [twitter] @{username:<18} no posts")
            continue

        summary = _summarize_user(username, tweets, summarize_llm, summarize_model, tracker)
        if summary is None:
            nothing_notable += 1
            print(f"  [twitter] @{username:<18} {len(tweets):>3} posts -> nothing notable")
            continue

        words = len(summary.split())
        print(f"  [twitter] @{username:<18} {len(tweets):>3} posts -> {words}w")
        summaries.append({
            "username":    username,
            "summary":     summary,
            "tweet_count": len(tweets),
            "url":         f"https://x.com/{username}",
        })

    print(
        f"[twitter] {len(summaries)} account(s) summarized"
        f" ({silent} silent, {nothing_notable} nothing notable)"
    )
    return summaries
