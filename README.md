# Research Newsletter Pipeline

An automated pipeline that searches the web for recent news on topics you define, filters the results with an LLM, and delivers a formatted PDF newsletter to your Telegram.

---

## How it works

1. **Search** — For each query you define in a config file, the agent calls [Exa.ai](https://exa.ai) to retrieve recent news articles. Exa returns AI-generated summaries focused specifically on your query.
2. **Filter** — An LLM (Claude Haiku or GPT-4o-mini) reads all article summaries and decides which are genuinely newsworthy. It also deduplicates — if five sources all cover the same announcement, only the best one is kept.
3. **Assemble** — Surviving articles are assembled into a newsletter using their titles and Exa-generated summaries. No second LLM call required.
4. **Deliver** — The newsletter is rendered as a PDF and sent to a Telegram chat.

Every run is logged to a local SQLite database (article count, token usage, cost). Prompts for de-duplication/filtering are configurable.

---

## Project structure

```
research-newsletter-pipeline/
├── configs/                  # One YAML file per newsletter
│   └── ai-research-claude.yaml
├── newsletter/
│   ├── pipeline.py           # Orchestrator — entry point
│   ├── research.py           # Exa search + LLM newsworthiness filter
│   ├── llm.py                # Provider-agnostic wrapper (Anthropic / OpenAI)
│   ├── publisher.py          # PDF generation + Telegram delivery
│   ├── cost.py               # Token and cost tracking
│   └── state.py              # SQLite run history
├── prompts/
│   └── newsworthiness.md     # Instructions for the filter LLM
├── schema/
│   └── init.sql              # SQLite schema
├── test_output/              # Markdown previews from --test runs
├── data/                     # Generated PDFs and state.db (gitignored)
├── .env.example              # API key template
└── requirements.txt
```

---

## Prerequisites

- Python 3.11+
- API keys for:
  - [Exa.ai](https://exa.ai) — web search
  - [Anthropic](https://console.anthropic.com) and/or [OpenAI](https://platform.openai.com) — LLM filtering
  - Telegram bot — delivery (see setup below)

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/your-username/research-newsletter-agent.git
cd research-newsletter-agent
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

TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

**Getting a Telegram bot:**
1. Message [@BotFather](https://t.me/BotFather) on Telegram and send `/newbot`
2. Copy the token it gives you → `TELEGRAM_BOT_TOKEN`
3. Start a conversation with your new bot, then open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and copy the `chat.id` value → `TELEGRAM_CHAT_ID`

### 3. Create a newsletter config

Create a YAML file in `configs/`. Example (`configs/ai-research-claude.yaml`):

```yaml
name: ai-research

search_queries:
  - LLM foundation model releases benchmarks
  - AI product launch announcements
  - AI hardware Nvidia GPU infrastructure
  - AI startup funding investment rounds
  - AI regulation policy safety and security

recency_days: 7       # only fetch articles from the last N days
num_results: 4        # articles fetched per query (before filtering)

provider: anthropic   # "anthropic" or "openai"
fast_model: claude-haiku-4-5  # model used for the newsworthiness filter
```

Each entry under `search_queries` is sent as a separate Exa search. More queries = broader coverage. `num_results` controls how many raw results come back per query before the LLM filters them.

---

## Running

### Test mode (recommended first run)

Saves a Markdown preview to `test_output/` instead of generating a PDF or sending a Telegram message:

```bash
python -m newsletter.pipeline --test configs/ai-research-claude.yaml
```

Output file: `test_output/ai-research-test-20260616.md`

### Full run (PDF + Telegram)

```bash
# Run a specific config
python -m newsletter.pipeline configs/ai-research-claude.yaml

# Run all configs in configs/
python -m newsletter.pipeline
```

### Example output

```
=== TEST RUN: ai-research-test-20260616 ===
Provider: anthropic | Model: claude-haiku-4-5

[research] Running 9 queries...
[research] Fetched 32 articles across all queries
[research] Newsworthiness filter: 19 kept, 13 dropped
=== Test run complete: ai-research-test-20260616 ===
Articles: 19
Tokens:   4821 in / 612 out
Cost:     $0.0079
Output:   test_output/ai-research-test-20260616.md
```

---

## Using OpenAI models

Change `provider` and `fast_model` in your config file:

```yaml
provider: openai
fast_model: gpt-4o-mini
```

Make sure `OPENAI_API_KEY` is set in your `.env`.

---

## Multiple newsletters

Create one YAML file per newsletter in `configs/`. Running `python -m newsletter.pipeline` (no arguments) discovers and runs all of them in sequence.

```
configs/
├── ai-research.yaml
├── biotech-weekly.yaml
└── fintech-digest.yaml
```

---

## Customising the filter

The LLM filter reads its instructions from `prompts/newsworthiness.md`. Edit that file to change what counts as newsworthy for your use case — what topics to include, what to exclude, and how to handle duplicate coverage of the same story.

---

## Run history

Every run is recorded to `data/state.db` (SQLite). You can inspect it with any SQLite browser, or query it directly:

```bash
sqlite3 data/state.db "SELECT run_id, status, num_queries, article_count, cost_usd FROM runs ORDER BY started_at DESC LIMIT 10;"
```

| Column | Description |
|---|---|
| `run_id` | Unique identifier for the run |
| `status` | `success`, `failed`, or `running` |
| `num_queries` | Number of search queries executed |
| `article_count` | Articles that passed the filter |
| `input_tokens` / `output_tokens` | LLM usage |
| `cost_usd` | Estimated cost of the run |

---

## Tech stack

| Component | Technology |
|---|---|
| Web search | [Exa.ai](https://exa.ai) neural search |
| LLM filtering | Anthropic Claude Haiku / OpenAI GPT-4o-mini |
| PDF generation | xhtml2pdf + Jinja2 |
| Delivery | python-telegram-bot |
| Run history | SQLite |
| Config | YAML |
