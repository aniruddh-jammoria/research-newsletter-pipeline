# Research Newsletter Pipeline

![License: MIT](https://img.shields.io/badge/license-MIT-blue)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![LLM: Claude / GPT / local](https://img.shields.io/badge/LLM-Claude%20%7C%20GPT%20%7C%20local-8A2BE2)

Turns a YAML file into a weekly PDF newsletter, delivered to your Telegram.

Staying current on a fast-moving field means either paying for a newsletter that covers
someone else's interests, or doing the sifting yourself every week. This does the sifting:
you define the topic, the sources and the accounts to follow, and each run searches, removes
duplicate coverage, discards the filler, writes its own summaries, and delivers a PDF. Define
as many newsletters as you want by adding config files — and run the whole reasoning half on
your own hardware, so a weekly issue costs cents or nothing at all.

## Demo

<!-- TODO: add screenshot/demo of a rendered PDF -->

## How it works

1. **You provide** a YAML file — search queries, academic domains, Twitter accounts — plus API
   keys in `.env`.
2. **Retrieval:** [Exa](https://exa.ai) searches news and papers; [getxapi](https://www.getxapi.com)
   fetches posts; your configured blogs and podcasts are read straight from their RSS/Atom feeds.
3. **Summarization:** your chosen model condenses every article and paper to a neutral 100-150
   words, each account's week of posts to 50-100 words, and each blog post or podcast episode to
   a single 30-word-or-fewer sentence. Titles are cleaned in the same pass.
4. **Filtering (news only):** one pass removes duplicate coverage of the same event, keeping the
   most authoritative source; a second judges what remains on its own merits.
5. **Output:** a PDF with an up-to-5-bullet overview, four sections, and delivery to Telegram.
   Every run is logged to SQLite and cached so it can be re-rendered for free.

The reasoning steps in 3 and 4 are the part that would otherwise cost money on every run.
Point them at Anthropic, OpenAI, or your own llama.cpp server — independently, per step.

## Quick start

```bash
git clone https://github.com/aniruddh-jammoria/research-newsletter-pipeline.git
cd research-newsletter-pipeline
pip install -r requirements.txt
```

Get API keys: [Exa](https://exa.ai) (search), [Anthropic](https://console.anthropic.com) or
[OpenAI](https://platform.openai.com) (skip if running fully local),
[getxapi](https://www.getxapi.com) (Twitter, optional), and a Telegram bot — message
[@BotFather](https://t.me/BotFather), send `/newbot`, then open
`https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` to find your `chat.id`.

```bash
cp .env.example .env    # then fill in your keys
cp examples/cloud.yaml configs/my-newsletter.yaml
```

Edit `search_queries` to your topic, then dry-run it — this writes a Markdown preview to
`test_output/` with no PDF and no Telegram message:

```bash
python -m newsletter.pipeline --test configs/my-newsletter.yaml
```

Once it looks right, run it for real:

```bash
python -m newsletter.pipeline configs/my-newsletter.yaml
```

Prefer to run entirely on your own hardware? Start from [`examples/local.yaml`](examples/local.yaml)
and see [docs/RUNNING-LOCALLY.md](docs/RUNNING-LOCALLY.md).

## Usage

**Run every newsletter.** Each YAML file in `configs/` is a separate newsletter; no arguments
discovers and runs all of them:

```bash
python -m newsletter.pipeline
```

**Re-publish a cached run.** Every successful run saves its assembled content, so you can
re-render and re-deliver without repeating any searches or LLM calls — useful when iterating on
formatting, since it costs nothing and takes seconds. The run ID is printed at the start of
every run:

```bash
python -m newsletter.pipeline --rerun ai-research-c66710
```

**Schedule it weekly.** See [docs/SCHEDULING.md](docs/SCHEDULING.md) — a Windows Task Scheduler
entry that runs in local time, survives daylight saving, and can wake the machine.

```
=== Newsletter run: ai-research-abc123 ===
Filter:    local | gemma-4-26B-A4B-it
Summarize: local | gemma-4-26B-A4B-it

[research]      50 unique articles found
[research]      50 in / 50 summarized in 18:23 (22.1s each) — Exa text: 50, scraped: 0, no content: 0 (0.0%), titles cleaned: 31
[research]      Dedup:  37 kept, 13 dropped
[research]      Filter: 27 kept, 10 dropped
[papers]        18 unique papers found
[blog_podcasts] 6 unique item(s) found across 5/5 source(s)
[twitter]       14 account(s) summarized (2 silent, 3 nothing notable)
[overview]      5 bullet(s) written

=== Done: ai-research-abc123 ===
Articles: 27 | Blogs/Podcasts: 6 | Papers: 18 | Tweets: 14
Cost:     $0.0000
PDF:      data/ai-research_2026-07-26.pdf
```

## Configuration & customization

Each newsletter is one YAML file in `configs/`:

```yaml
name: ai-research
file_name: ai-research   # output is {file_name}_{YYYY-MM-DD}.pdf

search_queries:                      # one Exa search each
  - AI model releases benchmarks open source weights
  - AI agents agentic workflows autonomous systems

research_papers:                     # domain-restricted search
  queries:
    - LLM reasoning planning alignment safety
  sources: [arxiv.org, nature.com, openreview.net]

twitter_accounts: [sama, karpathy]   # every post in the window is summarized

blog_podcasts:                       # each url must be a direct RSS/Atom feed
  - name: Simon Willison
    url: https://simonwillison.net/atom/everything/

recency_days: 7             # how far back to look
news_results: 5             # per search_queries entry
paper_results: 5            # per research_papers.queries entry
blog_podcast_results: 5     # per blog_podcasts entry

mode: cloud            # or "local" — sets the default provider for both steps below
model: claude-haiku-4-5

filter: {}             # inherits provider/model from mode
# summarize: {}        # omit to reuse the filter block
```

`filter` and `summarize` are independent — set `provider`/`model` inside either to override
what `mode` supplies, so you can filter on cheap cloud Claude while summarizing locally, or any
other mix. For OpenAI, use `provider: openai` with `model: gpt-4o-mini` and set `OPENAI_API_KEY`.

**Prompts.** Every LLM step reads editable instructions from `prompts/` — nothing is hardcoded.
Edit [`summarize.md`](prompts/summarize.md), [`deduplication.md`](prompts/deduplication.md),
[`newsworthiness.md`](prompts/newsworthiness.md), [`tweet_summary.md`](prompts/tweet_summary.md),
[`blog-podcast-summary.md`](prompts/blog-podcast-summary.md) or [`overview.md`](prompts/overview.md)
to change how strict, lenient or verbose that stage is.

**Templates.** The PDF layout is a single Jinja2 template at
`newsletter/templates/newsletter.html`.

See [`examples/cloud.yaml`](examples/cloud.yaml) and [`examples/local.yaml`](examples/local.yaml)
for complete, ready-to-copy configs, and [docs/PIPELINE.md](docs/PIPELINE.md) for what each stage
actually does and what a run costs.

## Architecture

Retrieval is unavoidably networked — there is no way to search the live web or fetch posts
without querying someone's index. Reasoning is not:

```
RETRIEVAL — always networked
Exa (news + papers)  ·  getxapi (posts)  ·  RSS/Atom feeds (blogs + podcasts)
                    |
                    v
REASONING — your choice, per step
summarizing · deduplicating · judging newsworthiness
   mode: cloud  ->  Anthropic / OpenAI   (pay per token)
   mode: local  ->  your llama.cpp server (free, private)
```

```
newsletter/
├── pipeline.py       # Orchestrator — entry point
├── research.py       # News search, dedup, newsworthiness filter
├── papers.py         # Academic paper search
├── twitter.py        # Post fetching + per-account summaries
├── blog_podcasts.py  # RSS/Atom feed fetching + per-item summaries
├── summarize.py      # Page text -> summary + clean title (per-section length/prompt)
├── overview.py       # The opening bullets
├── urls.py           # Same-document URL identity (arXiv forms, tracking params)
├── llm.py            # Provider-agnostic wrapper (Anthropic / OpenAI / local)
├── llama_server.py   # Auto start/stop for local llama.cpp servers
├── prompts.py        # Prompt loading
├── publisher.py      # PDF generation + Telegram delivery
├── cost.py           # Token and cost tracking
└── state.py          # SQLite run history

configs/    # One YAML per newsletter (auto-discovered)
examples/   # Ready-to-copy cloud and local templates
prompts/    # Editable instructions for every LLM step
scripts/    # Scheduled-run wrapper and task registration
docs/       # Pipeline detail, local models, scheduling
```

| Component | Technology |
|---|---|
| News & paper search | [Exa](https://exa.ai) neural search |
| Twitter/X | [getxapi](https://www.getxapi.com) |
| Blogs & podcasts | RSS/Atom feeds via feedparser |
| Reasoning | Anthropic Claude / OpenAI GPT / local llama.cpp |
| Scrape fallback | trafilatura |
| PDF | xhtml2pdf + Jinja2 |
| Delivery | python-telegram-bot |
| Run history | SQLite |

## Changelog & development notes

See [`Changelog.md`](Changelog.md) for what changed, why it mattered, and what impact it had.
Contributor and agent instructions live in [`CLAUDE.md`](CLAUDE.md).

## License

[MIT](LICENSE)
