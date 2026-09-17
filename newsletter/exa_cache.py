import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_CACHE_DIR = Path(__file__).parent.parent / "data" / "exa_cache"


def get_or_fetch(name: str, key_params: dict, fetch: Callable[[], dict]) -> dict:
    """Returns a cached Exa search result for today if one exists for these
    exact params, otherwise calls `fetch()` and caches its result.

    Exa search is the pipeline's only real per-run cost — the local model is
    free to rerun — so if a later stage (local model summarization, dedup,
    etc.) crashes partway through, retrying the same day reuses what was
    already paid for instead of re-querying Exa for the same articles.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = json.dumps({"date": date_str, **key_params}, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    cache_path = _CACHE_DIR / f"{name}_{date_str}_{digest}.json"

    if cache_path.exists():
        print(f"[exa_cache] Reusing cached '{name}' search results from earlier today — no Exa calls made")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    result = fetch()

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for stale in _CACHE_DIR.glob(f"{name}_*.json"):
        if stale != cache_path:
            stale.unlink(missing_ok=True)
    cache_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
