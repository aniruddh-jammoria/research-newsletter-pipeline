import os
from datetime import datetime, timedelta, timezone

import requests

_BASE = "https://api.getxapi.com"
_DATE_FMT = "%a %b %d %H:%M:%S +0000 %Y"  # "Thu Jun 04 21:19:49 +0000 2026"


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


def _fetch_user_tweets(username: str, since: str, num_results: int) -> list[dict]:
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

    tweets = []
    for t in resp.json().get("tweets", []):
        tweets.append({
            "username": username,
            "url": t.get("url", ""),
            "text": t.get("text", ""),
            "published_date": _parse_date(t.get("createdAt", "")),
            "_likes": t.get("likeCount", 0),
            "_retweets": t.get("retweetCount", 0),
        })

    # Return top N by engagement
    tweets.sort(key=lambda x: x["_likes"] + x["_retweets"], reverse=True)
    for t in tweets:
        t.pop("_likes")
        t.pop("_retweets")
    return tweets[:num_results]


def run_twitter(
    usernames: list[str],
    recency_days: int,
    num_results: int = 3,
) -> list[dict]:
    if not usernames:
        return []

    since = (datetime.now(timezone.utc) - timedelta(days=recency_days)).strftime("%Y-%m-%d")
    print(f"[twitter] Fetching tweets for {len(usernames)} accounts via getxapi (since {since}):")

    all_tweets: list[dict] = []
    for username in usernames:
        print(f"  · @{username}")
        tweets = _fetch_user_tweets(username, since, num_results)
        all_tweets.extend(tweets)

    print(f"[twitter] {len(all_tweets)} tweets found")
    return all_tweets
