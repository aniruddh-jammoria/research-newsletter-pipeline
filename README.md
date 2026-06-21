# Research Newsletter Pipeline

An automated pipeline that searches the web for recent AI news, filters results with an LLM, fetches research papers, pulls tweets from key accounts, and delivers a formatted PDF newsletter to your Telegram.

---

## How it works

The newsletter is built from three independent modules, each producing a section of the PDF:

1. **News & Analysis** — For each query in your config, [Exa.ai](https://exa.ai) retrieves recent news articles with AI-generated summaries. An LLM (Claude Haiku or GPT-4o-mini) then filters for genuine newsworthiness and deduplicates — if multiple sources cover the same announcement, only the best is kept.

2. **Research Papers** — Exa searches academic sources (`arxiv.org`, `nature.com`, `openreview.net`) using your paper queries, restricted by domain. Returns papers published within your recency window with abstract summaries. No LLM filter — domain + query restriction is targeted enough.

3. **Twitter Highlights** — Fetches real tweets from a configured list of accounts via [getxapi.com](https://www.getxapi.com). Uses advanced search (`from:username since:date -is:reply`) to get only original posts within the recency window. Returns top posts per account ranked by engagement.

The PDF is rendered with three colour-coded sections and delivered to Telegram. Every run is logged to a local SQLite database.

---

## Project structure

```
research-newsletter-pipeline/
├── configs/                  # One YAML file per newsletter
│   └── ai-research-claude.yaml
├── newsletter/
│   ├── pipeline.py           # Orchestrator — entry point
│   ├── research.py           # Exa search + LLM newsworthiness filter (news)
│   ├── papers.py             # Exa search for academic papers
│   ├── twitter.py            # getxapi Twitter/X integration
│   ├── llm.py                # Provider-agnostic wrapper (Anthropic / OpenAI)
│   ├── publisher.py          # PDF generation + Telegram delivery
│   ├── cost.py               # Token and cost tracking
│   └── state.py              # SQLite run history
├── prompts/
│   └── newsworthiness.md     # Instructions for the news filter LLM
├── schema/
│   └── init.sql              # SQLite schema
├── test_output/              # Markdown previews from --test runs
├── data/                     # Generated PDFs and state.db (gitignored)
├── .env.example              # API key template
├── UPDATE_LOG.md             # Changelog of pipeline improvements
└── requirements.txt
```

---

## Prerequisites

- Python 3.11+
- API keys for:
  - [Exa.ai](https://exa.ai) — news and paper search
  - [Anthropic](https://console.anthropic.com) and/or [OpenAI](https://platform.openai.com) — LLM filtering
  - [getxapi.com](https://www.getxapi.com) — Twitter/X (free tier: $0.10 credit on signup)
  - Telegram bot — delivery (see setup below)

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/your-username/research-newsletter-pipeline.git
cd research-newsletter-pipeline
pip install -r requirements.txt
```

### 2. Configure API keys

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...          # only needed if using OpenAI models
EXA_API_KEY=...
GETXAPI_KEY=...

TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

**Getting a Telegram bot:**
1. Message [@BotFather](https://t.me/BotFather) on Telegram and send `/newbot`
2. Copy the token it gives you → `TELEGRAM_BOT_TOKEN`
3. Start a conversation with your new bot, then open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and copy the `chat.id` value → `TELEGRAM_CHAT_ID`

### 3. Create a newsletter config

Create a YAML file in `configs/`. Full example:

```yaml
name: ai-research

# News & Analysis — each query is a separate Exa search
search_queries:
  - AI model releases benchmarks open source weights
  - Anthropic Claude model updates product features
  - OpenAI ChatGPT model updates product features
  - Google Gemini DeepMind model updates AI research
  - AI hardware Nvidia GPU infrastructure data center
  - AI startup funding investment rounds
  - AI regulation policy safety US EU
  - AI agents agentic workflows autonomous systems
  - Open source AI models Meta LLaMA Mistral community
  - AI coding developer tools Cursor Copilot Claude Code

# Research Papers — domain-restricted Exa search
research_papers:
  queries:
    - LLM reasoning planning alignment safety
    - multimodal vision language models image video
    - AI agents autonomous systems tool use
    - human-agent interaction human-AI collaboration
  sources:
    - arxiv.org
    - nature.com
    - openreview.net

# Twitter — real tweets fetched via getxapi.com
twitter_accounts:
  - sama
  - DarioAmodei
  - karpathy
  - ylecun
  - emollick
  - simonw

recency_days: 7       # fetch content from the last N days
num_results: 5        # results per news query (before LLM filter)

provider: anthropic
fast_model: claude-haiku-4-5
```

---

## Running

### Dry run (recommended first)

Saves a Markdown preview to `test_output/` — no PDF, no Telegram message:

```bash
python -m newsletter.pipeline --test configs/ai-research-claude.yaml
```

### Full run (PDF + Telegram)

```bash
# Single config
python -m newsletter.pipeline configs/ai-research-claude.yaml

# All configs in configs/
python -m newsletter.pipeline
```

### Re-publish a cached run

Every successful run saves the assembled content to `data/{run_id}.json`. To re-render and re-deliver without repeating any searches or LLM calls:

```bash
python -m newsletter.pipeline --rerun ai-research-c66710
```

The run ID is printed at the start of every run. Use this when iterating on template or formatting changes — it costs nothing and takes a few seconds.


### Example output

```
=== Newsletter run: ai-research-abc123 ===
Provider: anthropic | Model: claude-haiku-4-5

[research] Running 10 queries (recency: 7d, 5 results each)
[research] 42 unique articles found
[research] Filter: 18 kept, 24 dropped

[papers] Searching 4 queries on ['arxiv.org', 'nature.com', 'openreview.net']
[papers] 17 unique papers found

[twitter] Fetching tweets for 19 accounts via getxapi (since 2026-06-14)
[twitter] 25 tweets found

=== Done: ai-research-abc123 ===
Articles: 18 | Papers: 17 | Tweets: 25
Tokens:   4821 in / 612 out
Cost:     $0.0079
PDF:      data/newsletter-ai-research.pdf
```

---

## Exa query count per run

| Module | Queries |
|---|---|
| News (10 queries × 1 call each) | 10 |
| Papers (4 queries × 1 call each) | 4 |
| Twitter (19 accounts × 1 call each) | 19 |
| **Total** | **33** |

---

## Using OpenAI models

```yaml
provider: openai
fast_model: gpt-4o-mini
```

Make sure `OPENAI_API_KEY` is set in `.env`.

---

## Multiple newsletters

Create one YAML file per newsletter in `configs/`. Running without arguments discovers and runs all of them:

```bash
python -m newsletter.pipeline
```

---

## Customising the filter

Edit `prompts/newsworthiness.md` to change what the LLM considers newsworthy — topics to include/exclude, how to handle duplicate coverage, etc. This only applies to the News section; papers and tweets are not LLM-filtered.

---

## Run history

Every run is logged to `data/state.db` (SQLite):

```bash
sqlite3 data/state.db "SELECT run_id, status, article_count, cost_usd FROM runs ORDER BY started_at DESC LIMIT 10;"
```

---

## Tech stack

| Component | Technology |
|---|---|
| News search | [Exa.ai](https://exa.ai) neural search |
| Paper search | [Exa.ai](https://exa.ai) with domain restriction |
| Twitter/X | [getxapi.com](https://www.getxapi.com) ($0.001/call) |
| LLM filtering | Anthropic Claude Haiku / OpenAI GPT-4o-mini |
| PDF generation | xhtml2pdf + Jinja2 |
| Delivery | python-telegram-bot |
| Run history | SQLite |
| Config | YAML |
