import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from . import blog_podcasts as blog_podcasts_mod
from . import llama_server
from . import overview as overview_mod
from . import papers as papers_mod
from . import publisher, research, state
from . import twitter as twitter_mod
from .cost import CostTracker
from .llm import LLMClient

_ROOT = Path(__file__).parent.parent
_CONFIGS_DIR = _ROOT / "configs"
_TEST_OUTPUT_DIR = _ROOT / "test_output"
_DATA_DIR = _ROOT / "data"


def _save_cache(run_id: str, output_name: str, newsletter: dict, cost_usd: float) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    cache = {"run_id": run_id, "output_name": output_name, "cost_usd": cost_usd, "newsletter": newsletter}
    (_DATA_DIR / f"{run_id}.json").write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _load_cache(run_id: str) -> dict:
    path = _DATA_DIR / f"{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No cached run found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


_MODE_SHARED_KEYS = ("provider", "model", "local_base_url", "local_server_exe", "local_model_path", "local_server_args")


def _mode_defaults(cfg: dict) -> dict:
    """Shared defaults for `filter`/`summarize`, derived from top-level `mode` plus
    any of the shared keys set at the top level. Lets `mode: local` (or `cloud`) plus a
    single set of local_* keys apply to both blocks, instead of duplicating them twice.
    Explicit values inside a `filter:`/`summarize:` block always take precedence."""
    mode = cfg.get("mode")
    defaults = {}
    if mode == "cloud":
        defaults["provider"] = "anthropic"
    elif mode == "local":
        defaults["provider"] = "local"
    elif mode is not None:
        raise ValueError(f"Unknown mode: {mode!r} — use 'cloud' or 'local'")

    for key in _MODE_SHARED_KEYS:
        if key in cfg:
            defaults[key] = cfg[key]
    return defaults


def _resolve_filter_summarize_cfg(cfg: dict) -> tuple[dict, dict]:
    """Resolve the `filter:` and `summarize:` blocks.

    Every article is summarized from its own page text now, so `summarize` is
    always needed. Omitting the block reuses the `filter` block as-is.
    """
    mode_defaults = _mode_defaults(cfg)
    filter_cfg = {**mode_defaults, **cfg.get("filter", {})}
    summarize_cfg = {**mode_defaults, **cfg["summarize"]} if "summarize" in cfg else filter_cfg
    return filter_cfg, summarize_cfg


def _build_llm_for(block: dict) -> tuple[LLMClient, str]:
    """Build an LLMClient from a `filter:` or `summarize:` config block."""
    provider = block.get("provider", "anthropic")
    model    = block.get("model", "claude-haiku-4-5")

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY not set")
        return LLMClient(provider=provider, api_key=api_key), model

    if provider == "local":
        base_url = block.get("local_base_url", "http://localhost:8080/v1")
        return LLMClient(provider=provider, api_key="not-needed", base_url=base_url), model

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set")
    return LLMClient(provider=provider, api_key=api_key), model


def _assemble(
    articles: list[dict],
    papers: list[dict] | None = None,
    tweets: list[dict] | None = None,
    overview: list[str] | None = None,
    blog_podcasts: list[dict] | None = None,
) -> dict:
    return {
        "newsletter_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "overview": overview or [],
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
        "blog_podcasts": [
            {
                "title":          b["title"],
                "summary":        b["summary"],
                "source":         b["source_name"],
                "url":            b["url"],
                "published_date": b.get("published_date", ""),
            }
            for b in (blog_podcasts or [])
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
        f"*Generated: {meta['generated_at']} | Articles: {meta['article_count']} | Blogs/Podcasts: {meta['blog_podcast_count']} | Papers: {meta['paper_count']} | Tweets: {meta['tweet_count']} | Cost: ${meta['cost_usd']:.4f} | Run: {meta['run_id']}*",
        "",
    ]

    if newsletter.get("overview"):
        lines += ["## This Week's Overview", ""]
        lines += [f"- {point}" for point in newsletter["overview"]]
        lines += [""]

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

    if newsletter.get("blog_podcasts"):
        lines += ["", "---", "", "## Blogposts & Podcasts", ""]
        for b in newsletter["blog_podcasts"]:
            lines += [
                "---",
                "",
                f"### {b['title']}",
                f"*{b['published_date'][:10]} — {b['source']}*",
                "",
                b["summary"],
                "",
                f"[Read more]({b['url']})",
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
        for t in newsletter["tweets"]:
            lines += [
                f"### @{t['username']}",
                f"*{t.get('tweet_count', 0)} posts*",
                "",
                t["summary"],
                "",
                f"[View profile]({t['url']})",
                "",
            ]

    return "\n".join(lines)


def _parse_papers_cfg(cfg: dict) -> tuple[list[str], list[str]]:
    papers_cfg = cfg.get("research_papers", {})
    if not isinstance(papers_cfg, dict):
        return [], []
    return papers_cfg.get("queries", []), papers_cfg.get("sources", [])


def _parse_blog_podcasts_cfg(cfg: dict) -> list[dict]:
    sources = cfg.get("blog_podcasts", [])
    return sources if isinstance(sources, list) else []


def run(config_path: Path) -> dict:
    cfg = load_config(config_path)
    search_queries    = cfg["search_queries"]
    recency_days      = cfg.get("recency_days", 7)
    news_results      = cfg.get("news_results", 5)
    paper_results     = cfg.get("paper_results", 5)
    name              = cfg.get("name", config_path.stem)
    file_name         = cfg.get("file_name", name)
    paper_queries, paper_sources = _parse_papers_cfg(cfg)
    twitter_accounts  = cfg.get("twitter_accounts", [])
    blog_podcast_sources = _parse_blog_podcasts_cfg(cfg)
    blog_podcast_results = cfg.get("blog_podcast_results", 5)

    filter_cfg, summarize_cfg = _resolve_filter_summarize_cfg(cfg)

    filter_llm, filter_model       = _build_llm_for(filter_cfg)
    summarize_llm, summarize_model = _build_llm_for(summarize_cfg)

    run_id = f"{name}-{uuid.uuid4().hex[:6]}"
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_name = f"{file_name}_{date_str}"
    print(f"\n=== Newsletter run: {run_id} ===")
    print(f"Filter:    {filter_cfg.get('provider', 'anthropic')} | {filter_model}")
    print(f"Summarize: {summarize_cfg.get('provider', 'anthropic')} | {summarize_model}")
    print()

    state.start_run(run_id)
    tracker = CostTracker()

    started_urls = [url for url in (
        llama_server.ensure_running(filter_cfg),
        llama_server.ensure_running(summarize_cfg),
    ) if url is not None]

    try:
        articles = research.run_research(
            search_queries, recency_days, news_results, filter_llm, filter_model, tracker,
            summarize_llm=summarize_llm, summarize_model=summarize_model,
            run_id=run_id,
        )
        if not articles:
            raise RuntimeError("No articles passed the newsworthiness filter")

        papers = papers_mod.run_papers(
            paper_queries, paper_sources, recency_days, num_results=paper_results,
            summarize_llm=summarize_llm, summarize_model=summarize_model,
            tracker=tracker,
        ) if paper_queries else []
        tweets = twitter_mod.run_twitter(
            twitter_accounts, recency_days, summarize_llm, summarize_model, tracker,
        ) if twitter_accounts else []
        blog_podcasts = blog_podcasts_mod.run_blog_podcasts(
            blog_podcast_sources, recency_days, num_results=blog_podcast_results,
            summarize_llm=summarize_llm, summarize_model=summarize_model,
            tracker=tracker,
        ) if blog_podcast_sources else []
        overview = overview_mod.generate(articles, summarize_llm, summarize_model, tracker)

        newsletter = _assemble(articles, papers=papers, tweets=tweets, overview=overview, blog_podcasts=blog_podcasts)
        summary = tracker.summary()
        _save_cache(run_id, output_name, newsletter, summary["cost_usd"])
        pdf_path = publisher.run_publisher(newsletter, run_id, output_name, summary["cost_usd"])

        state.finish_run(
            run_id, status="success",
            num_queries=len(search_queries),
            article_count=len(articles),
            input_tokens=summary["input_tokens"],
            output_tokens=summary["output_tokens"],
            cost_usd=summary["cost_usd"],
        )

        print(f"\n=== Done: {run_id} ===")
        print(f"Articles: {len(articles)} | Blogs/Podcasts: {len(blog_podcasts)} | Papers: {len(papers)} | Tweets: {len(tweets)}")
        print(f"Tokens:   {summary['input_tokens']} in / {summary['output_tokens']} out")
        print(f"Cost:     ${summary['cost_usd']:.4f}")
        print(f"PDF:      {pdf_path}")
        return {"run_id": run_id, "pdf_path": str(pdf_path), **summary}

    except Exception as e:
        state.finish_run(run_id, status="failed", error=str(e))
        print(f"\n[pipeline] Run {run_id} failed: {e}")
        raise
    finally:
        for url in started_urls:
            llama_server.stop(url)


def run_test(config_path: Path) -> dict:
    cfg = load_config(config_path)
    search_queries    = cfg["search_queries"]
    recency_days      = cfg.get("recency_days", 7)
    news_results      = cfg.get("news_results", 5)
    paper_results     = cfg.get("paper_results", 5)
    name              = cfg.get("name", config_path.stem)
    file_name         = cfg.get("file_name", name)
    paper_queries, paper_sources = _parse_papers_cfg(cfg)
    twitter_accounts  = cfg.get("twitter_accounts", [])
    blog_podcast_sources = _parse_blog_podcasts_cfg(cfg)
    blog_podcast_results = cfg.get("blog_podcast_results", 5)

    filter_cfg, summarize_cfg = _resolve_filter_summarize_cfg(cfg)

    filter_llm, filter_model       = _build_llm_for(filter_cfg)
    summarize_llm, summarize_model = _build_llm_for(summarize_cfg)

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    run_id = f"{name}-test-{date_str}-{uuid.uuid4().hex[:6]}"
    output_name = f"{file_name}_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    print(f"\n=== TEST RUN: {run_id} ===")
    print(f"Filter:    {filter_cfg.get('provider', 'anthropic')} | {filter_model}")
    print(f"Summarize: {summarize_cfg.get('provider', 'anthropic')} | {summarize_model}")
    print()

    state.start_run(run_id)
    tracker = CostTracker()

    started_urls = [url for url in (
        llama_server.ensure_running(filter_cfg),
        llama_server.ensure_running(summarize_cfg),
    ) if url is not None]

    try:
        articles = research.run_research(
            search_queries, recency_days, news_results, filter_llm, filter_model, tracker,
            summarize_llm=summarize_llm, summarize_model=summarize_model,
            run_id=run_id,
        )
        if not articles:
            raise RuntimeError("No articles passed the newsworthiness filter")

        papers = papers_mod.run_papers(
            paper_queries, paper_sources, recency_days, num_results=paper_results,
            summarize_llm=summarize_llm, summarize_model=summarize_model,
            tracker=tracker,
        ) if paper_queries else []
        tweets = twitter_mod.run_twitter(
            twitter_accounts, recency_days, summarize_llm, summarize_model, tracker,
        ) if twitter_accounts else []
        blog_podcasts = blog_podcasts_mod.run_blog_podcasts(
            blog_podcast_sources, recency_days, num_results=blog_podcast_results,
            summarize_llm=summarize_llm, summarize_model=summarize_model,
            tracker=tracker,
        ) if blog_podcast_sources else []
        overview = overview_mod.generate(articles, summarize_llm, summarize_model, tracker)

        newsletter = _assemble(articles, papers=papers, tweets=tweets, overview=overview, blog_podcasts=blog_podcasts)
        summary = tracker.summary()
        _save_cache(run_id, output_name, newsletter, summary["cost_usd"])
        meta = {
            "run_id":        run_id,
            "generated_at":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "article_count": len(articles),
            "blog_podcast_count": len(blog_podcasts),
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
        print(f"Articles: {len(articles)} | Blogs/Podcasts: {len(blog_podcasts)} | Papers: {len(papers)} | Tweets: {len(tweets)}")
        print(f"Tokens:   {summary['input_tokens']} in / {summary['output_tokens']} out")
        print(f"Cost:     ${summary['cost_usd']:.4f}")
        print(f"Output:   {md_path}")
        return {"run_id": run_id, "md_path": str(md_path), **summary}

    except Exception as e:
        state.finish_run(run_id, status="failed", error=str(e))
        print(f"\n[pipeline] Run {run_id} failed: {e}")
        raise
    finally:
        for url in started_urls:
            llama_server.stop(url)


def run_rerun(run_id: str) -> dict:
    cache = _load_cache(run_id)
    newsletter  = cache["newsletter"]
    output_name = cache["output_name"]
    cost_usd    = cache["cost_usd"]

    print(f"\n=== Re-publishing: {run_id} ===")
    print(f"Articles: {len(newsletter.get('sections', []))} | Blogs/Podcasts: {len(newsletter.get('blog_podcasts', []))} | Papers: {len(newsletter.get('papers', []))} | Tweets: {len(newsletter.get('tweets', []))}")

    pdf_path = publisher.run_publisher(newsletter, run_id, output_name, cost_usd)
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
