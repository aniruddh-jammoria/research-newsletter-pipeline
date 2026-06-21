import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from . import papers as papers_mod
from . import publisher, research, state
from . import twitter as twitter_mod
from .cost import CostTracker
from .llm import LLMClient

_ROOT = Path(__file__).parent.parent
_CONFIGS_DIR = _ROOT / "configs"
_TEST_OUTPUT_DIR = _ROOT / "test_output"
_DATA_DIR = _ROOT / "data"


def _save_cache(run_id: str, name: str, newsletter: dict, cost_usd: float) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    cache = {"run_id": run_id, "name": name, "cost_usd": cost_usd, "newsletter": newsletter}
    (_DATA_DIR / f"{run_id}.json").write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _load_cache(run_id: str) -> dict:
    path = _DATA_DIR / f"{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No cached run found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_llm(cfg: dict) -> tuple[LLMClient, str]:
    provider   = cfg.get("provider", "anthropic")
    fast_model = cfg.get("fast_model", "claude-haiku-4-5")

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY not set")
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set")

    return LLMClient(provider=provider, api_key=api_key), fast_model


def _assemble(
    articles: list[dict],
    papers: list[dict] | None = None,
    tweets: list[dict] | None = None,
) -> dict:
    return {
        "newsletter_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "sections": [
            {
                "headline": a["title"],
                "summary":  a["summary"],
                "source":   a["source_domain"],
                "url":      a["url"],
                "published_date": a.get("published_date", ""),
            }
            for a in articles
        ],
        "papers": [
            {
                "title":          p["title"],
                "summary":        p["summary"],
                "source":         p["source_domain"],
                "url":            p["url"],
                "published_date": p.get("published_date", ""),
            }
            for p in (papers or [])
        ],
        "tweets": tweets or [],
    }


def _to_markdown(newsletter: dict, meta: dict) -> str:
    lines = [
        f"# Research Newsletter — {newsletter['newsletter_date']}",
        "",
        f"*Generated: {meta['generated_at']} | Articles: {meta['article_count']} | Papers: {meta['paper_count']} | Tweets: {meta['tweet_count']} | Cost: ${meta['cost_usd']:.4f} | Run: {meta['run_id']}*",
        "",
    ]

    for s in newsletter["sections"]:
        lines += [
            "---",
            "",
            f"### {s['headline']}",
            f"*{s['published_date'][:10]} — {s['source']}*",
            "",
            s["summary"],
            "",
            f"[Read more]({s['url']})",
            "",
        ]

    if newsletter.get("papers"):
        lines += ["", "---", "", "## Research Papers", ""]
        for p in newsletter["papers"]:
            lines += [
                "---",
                "",
                f"### {p['title']}",
                f"*{p['published_date'][:10]} — {p['source']}*",
                "",
                p["summary"],
                "",
                f"[Read paper]({p['url']})",
                "",
            ]

    if newsletter.get("tweets"):
        lines += ["", "---", "", "## Twitter Highlights", ""]
        current_user = None
        for t in newsletter["tweets"]:
            if t["username"] != current_user:
                current_user = t["username"]
                lines += [f"### @{current_user}", ""]
            lines += [
                f"*{t['published_date'][:10]}*" if t.get("published_date") else "",
                t["text"],
                "",
                f"[View tweet]({t['url']})",
                "",
            ]

    return "\n".join(lines)


def _parse_papers_cfg(cfg: dict) -> tuple[list[str], list[str]]:
    papers_cfg = cfg.get("research_papers", {})
    if not isinstance(papers_cfg, dict):
        return [], []
    return papers_cfg.get("queries", []), papers_cfg.get("sources", [])


def run(config_path: Path) -> dict:
    cfg = load_config(config_path)
    search_queries    = cfg["search_queries"]
    recency_days      = cfg.get("recency_days", 7)
    num_results       = cfg.get("num_results", 10)
    name              = cfg.get("name", config_path.stem)
    paper_queries, paper_sources = _parse_papers_cfg(cfg)
    twitter_accounts  = cfg.get("twitter_accounts", [])

    llm, fast_model = _build_llm(cfg)
    run_id = f"{name}-{uuid.uuid4().hex[:6]}"
    print(f"\n=== Newsletter run: {run_id} ===")
    print(f"Provider: {cfg.get('provider', 'anthropic')} | Model: {fast_model}\n")

    state.start_run(run_id)
    tracker = CostTracker()

    try:
        articles = research.run_research(search_queries, recency_days, num_results, llm, fast_model, tracker)
        if not articles:
            raise RuntimeError("No articles passed the newsworthiness filter")

        papers = papers_mod.run_papers(paper_queries, paper_sources, recency_days) if paper_queries else []
        tweets = twitter_mod.run_twitter(twitter_accounts, recency_days) if twitter_accounts else []

        newsletter = _assemble(articles, papers, tweets)
        summary = tracker.summary()
        _save_cache(run_id, name, newsletter, summary["cost_usd"])
        pdf_path = publisher.run_publisher(newsletter, run_id, name, summary["cost_usd"])

        state.finish_run(
            run_id, status="success",
            num_queries=len(search_queries),
            article_count=len(articles),
            input_tokens=summary["input_tokens"],
            output_tokens=summary["output_tokens"],
            cost_usd=summary["cost_usd"],
        )

        print(f"\n=== Done: {run_id} ===")
        print(f"Articles: {len(articles)} | Papers: {len(papers)} | Tweets: {len(tweets)}")
        print(f"Tokens:   {summary['input_tokens']} in / {summary['output_tokens']} out")
        print(f"Cost:     ${summary['cost_usd']:.4f}")
        print(f"PDF:      {pdf_path}")
        return {"run_id": run_id, "pdf_path": str(pdf_path), **summary}

    except Exception as e:
        state.finish_run(run_id, status="failed", error=str(e))
        print(f"\n[pipeline] Run {run_id} failed: {e}")
        raise


def run_test(config_path: Path) -> dict:
    cfg = load_config(config_path)
    search_queries    = cfg["search_queries"]
    recency_days      = cfg.get("recency_days", 7)
    num_results       = cfg.get("num_results", 10)
    name              = cfg.get("name", config_path.stem)
    paper_queries, paper_sources = _parse_papers_cfg(cfg)
    twitter_accounts  = cfg.get("twitter_accounts", [])

    llm, fast_model = _build_llm(cfg)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    run_id = f"{name}-test-{date_str}"
    print(f"\n=== TEST RUN: {run_id} ===")
    print(f"Provider: {cfg.get('provider', 'anthropic')} | Model: {fast_model}\n")

    state.start_run(run_id)
    tracker = CostTracker()

    try:
        articles = research.run_research(search_queries, recency_days, num_results, llm, fast_model, tracker)
        if not articles:
            raise RuntimeError("No articles passed the newsworthiness filter")

        papers = papers_mod.run_papers(paper_queries, paper_sources, recency_days) if paper_queries else []
        tweets = twitter_mod.run_twitter(twitter_accounts, recency_days) if twitter_accounts else []

        newsletter = _assemble(articles, papers, tweets)
        summary = tracker.summary()
        _save_cache(run_id, name, newsletter, summary["cost_usd"])
        meta = {
            "run_id":        run_id,
            "generated_at":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "article_count": len(articles),
            "paper_count":   len(papers),
            "tweet_count":   len(tweets),
            "cost_usd":      summary["cost_usd"],
        }

        _TEST_OUTPUT_DIR.mkdir(exist_ok=True)
        md_path = _TEST_OUTPUT_DIR / f"{run_id}.md"
        md_path.write_text(_to_markdown(newsletter, meta), encoding="utf-8")

        state.finish_run(
            run_id, status="success",
            num_queries=len(search_queries),
            article_count=len(articles),
            input_tokens=summary["input_tokens"],
            output_tokens=summary["output_tokens"],
            cost_usd=summary["cost_usd"],
        )

        print(f"\n=== Test run complete: {run_id} ===")
        print(f"Articles: {len(articles)} | Papers: {len(papers)} | Tweets: {len(tweets)}")
        print(f"Tokens:   {summary['input_tokens']} in / {summary['output_tokens']} out")
        print(f"Cost:     ${summary['cost_usd']:.4f}")
        print(f"Output:   {md_path}")
        return {"run_id": run_id, "md_path": str(md_path), **summary}

    except Exception as e:
        state.finish_run(run_id, status="failed", error=str(e))
        print(f"\n[pipeline] Run {run_id} failed: {e}")
        raise


def run_rerun(run_id: str) -> dict:
    cache = _load_cache(run_id)
    newsletter = cache["newsletter"]
    name       = cache["name"]
    cost_usd   = cache["cost_usd"]

    print(f"\n=== Re-publishing: {run_id} ===")
    print(f"Articles: {len(newsletter.get('sections', []))} | Papers: {len(newsletter.get('papers', []))} | Tweets: {len(newsletter.get('tweets', []))}")

    pdf_path = publisher.run_publisher(newsletter, run_id, name, cost_usd)
    print(f"PDF: {pdf_path}")
    return {"run_id": run_id, "pdf_path": str(pdf_path)}


def run_all() -> list[dict]:
    config_files = sorted(_CONFIGS_DIR.glob("*.yaml"))
    if not config_files:
        print(f"No config files found in {_CONFIGS_DIR}/")
        return []

    print(f"Found {len(config_files)} newsletter config(s): {[f.name for f in config_files]}")
    results = []
    for config_path in config_files:
        print(f"\n{'=' * 60}\nRunning: {config_path.name}\n{'=' * 60}")
        try:
            results.append(run(config_path))
        except Exception as e:
            print(f"[pipeline] {config_path.name} failed: {e}")
            results.append({"config": config_path.name, "error": str(e)})
    return results


if __name__ == "__main__":
    load_dotenv()
    state.init_db()

    parser = argparse.ArgumentParser(description="Research Newsletter Pipeline")
    parser.add_argument("config", nargs="?", type=Path, help="Single config file to run")
    parser.add_argument("--test",  action="store_true", help="Save markdown to test_output/ instead of publishing")
    parser.add_argument("--rerun", metavar="RUN_ID",    help="Re-publish a cached run without re-fetching content")
    args = parser.parse_args()

    if args.rerun:
        run_rerun(args.rerun)
    elif args.test:
        config_path = args.config or sorted(_CONFIGS_DIR.glob("*.yaml"))[0]
        run_test(config_path)
    elif args.config:
        run(args.config)
    else:
        run_all()
