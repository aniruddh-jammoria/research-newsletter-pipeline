# Pipeline Update Log

A running record of structural features and pipeline improvements.
Config changes (search queries, Twitter accounts) are not logged here.

---

## 2026-06-21

### Added Research Papers module
Introduced `newsletter/papers.py` as a second content source. Searches academic paper sites via Exa with `include_domains` restriction so results stay on-domain. No LLM filter — domain + query restriction is targeted enough.

Supported sources: `arxiv.org`, `nature.com`, `openreview.net`. Configurable via `research_papers.queries` and `research_papers.sources` in the newsletter YAML.

---

### Added Twitter/X module via getxapi
Introduced `newsletter/twitter.py` as a third content source. Fetches real tweets from a configured list of accounts using the [getxapi.com](https://www.getxapi.com) API (`$0.001/call`).

Uses advanced search: `from:{username} since:{date} -is:reply`. Returns top N tweets per account ranked by engagement (likes + retweets). Exa-based approach (finding tweet aggregator sites) was evaluated and discarded — coverage was inconsistent and content was indirect.

---

### Newsletter split into 3 named sections
The PDF now has three explicit sections — **News & Analysis**, **Research Papers**, **Twitter Highlights** — each with its own `<h2>` heading. Previously the newsletter was a flat undifferentiated list of articles.

---

### `--rerun` flag for re-publishing without re-fetching
Every successful run now saves the assembled newsletter to `data/{run_id}.json`. The `--rerun` flag loads that cache and re-renders + re-delivers without any Exa searches or LLM calls.

```
python -m newsletter.pipeline --rerun ai-research-c66710
```

Useful for testing template or formatting changes against real content.

---

### LLM filter JSON retry on parse failure
The newsworthiness filter sometimes returned malformed JSON (usually due to unescaped quotes in article titles). Added a retry: if `json.loads` fails, the bad output is sent back to the LLM with a fix request before raising an error.

---

### Sentence truncation for summaries
Added a `truncate_sentences(n)` Jinja2 filter in `publisher.py`. Applied to news summaries (4 sentences), paper abstracts (4 sentences), and tweet text (2 sentences). Handles both prose (splits on `.!?`) and Exa's bullet-point format (splits on `\n\n` or `\n` before a bullet character). Single mid-sentence line wraps are preserved.

---

### Newsletter formatting improvements
- News & Analysis: article link (`[See article]`) moved inline next to date, below headline. Raw URL removed.
- Research Papers: paper link (`[See paper]`) shown inline next to date. Raw URL removed.
- Twitter: each tweet shown as a bullet — `• [date] text... See tweet` — grouped by username under a single `@handle` heading.
