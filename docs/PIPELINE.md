# How the pipeline works

Detail behind the summary in the [README](../README.md). Covers what each stage does,
which prompt controls it, and what a run costs.

---

## Stage order

```
Exa search (news)   Feeds (blogposts/podcasts)   Exa search (papers)   getxapi (tweets)
      |                        |                         |                    |
      v                        v                         v                    v
  summarize                summarize                 summarize          summarize per account
  100-150 words             100-150 words              100-150 words       50-100 words
      |                        |                         |                    |
      v                        |                         |                    |
   dedup                       |                         |                    |
      |                        |                         |                    |
      v                        |                         |                    |
 newsworthiness                |                         |                    |
      |                        |                         |                    |
      +--> overview (<=5 bullets)                        |                    |
      |                        |                         |                    |
      +------------------------+-------------------------+--------------------+
                                |
                                v
                       PDF --> Telegram
```

Only the News section is filtered. Blogposts/Podcasts and Papers rely on the source list
(or domain + query restriction) being targeted enough; tweets are summarized per account
rather than selected.

---

## Summarization

Every article and paper is condensed to 100-150 words **before** any filtering, and that
summary is what the dedup pass, the newsworthiness pass, and the printed newsletter all
use. The same call also returns a cleaned title.

- Content comes from the page text Exa already bundles with each search result — no
  separate scrape, and no extra charge (see [Costs](#costs) below)
- If Exa returns no text for a page, it is scraped directly with `trafilatura` as a fallback
- If both fail, the item is dropped and counted rather than carried forward blank — a blank
  summary cannot be judged, cannot be printed, and several blanks in one batch look like
  duplicates of each other to the dedup pass
- Every run reports the split: how many items used Exa text, how many needed scraping, how
  many had no content, and how many titles were cleaned. The same numbers land in
  `logs/{run_id}.json`
- A local `summarize` model reports $0.00 for this step; a cloud one is tracked and priced

**Why before rather than after.** Summarization used to run on the survivors, so both filter
passes judged Exa's own summary — which is generated per search query, meaning two outlets
covering one announcement got summaries angled at whatever query found them. That worked
against the dedup pass, which has to recognise them as the same event. Writing one neutral
summary up front fixes that, and since the same text is reused for the newsletter it
replaces the old post-filter pass rather than adding a second one.

**Titles are extracted, not invented.** Search results carry the page's `<title>` tag, which
routinely includes the outlet name (`| TechCrunch`, `\ Anthropic`), navigation breadcrumbs,
arXiv identifiers, or — when extraction goes wrong — a section heading like `1. Introduction`.
Since the summarize step already reads the full text, it also reports the title *as the
document itself states it*. That is a lookup in text the model is already processing, not a
headline-writing task, so it costs no extra call. If no usable title comes back, the original
is kept unchanged.

## Deduplication

Two tiers, cheapest first.

**Document identity** (no LLM). Results are keyed by the document rather than the URL string,
so `arxiv.org/abs/`, `/html/` and `/pdf/` forms of one paper — with or without a version
suffix — collapse to a single entry, and tracking parameters do not create false distinctions.
arXiv links are normalised to the `/abs/` landing page. This is preventative for news, where
measurement showed no such duplicates occur in practice, and load-bearing for papers, where a
single paper genuinely does arrive under multiple URLs.

**Duplicate coverage** (LLM, news only). Groups articles reporting the same underlying event
and keeps one per group, preferring the official source, then a major outlet, then anything
else. In a representative run this collapsed four third-party Claude Opus 5 stories into
Anthropic's own announcement, and did the same for Gemini and OpenAI releases.

## Newsworthiness

Judges each surviving article on its own merits — relevance to your configured search queries,
recency, and exclusion of opinion pieces, listicles, roundups, press releases and paywalled
pages. Explicitly *not* comparative: the dedup pass already handled that.

## Overview

One extra call after filtering produces the up-to-5 bullet opener, seeing only articles that
made the newsletter. It is non-fatal by design: on failure the run logs it and continues, and
the section is omitted.

The same bullets are sent to Telegram with the PDF, so the summary is readable without opening
the attachment. Telegram caps a media caption at 1024 characters; when the bullets do not fit,
they are sent as a separate follow-up message rather than truncated.

## Twitter

Every post an account made in the window is read together and condensed into one 50-100 word
paragraph covering ideas, announcements and technical observations. There is no engagement
ranking or top-N cut, since nothing is being selected. Accounts whose week held nothing
substantive are dropped rather than padded.

## Blogposts & Podcasts

Each configured `{name, url}` source is fetched and parsed directly as an RSS/Atom feed —
`url` must already be a feed URL. There is no autodiscovery and no page scraping to find a
feed: a source that fails to fetch, or whose content doesn't parse as a feed with entries, is
skipped with a named warning at run time. Keeping this deliberately narrow means every
configured source is a known-good feed, hand-verified once when it is added.

Entries are filtered to `recency_days`, deduplicated by document identity across all sources
combined (the same URL check used by News/Papers), and capped per source by
`blog_podcast_results`. When a feed entry's own content is too short to be more than a
teaser, the item's text is left blank and picked up by the same scrape-the-URL fallback the
summarizer already uses for News/Papers — no separate logic needed. Podcasts are summarized
from their feed's show notes/description only; there is no audio transcription.

---

## Prompts

Every LLM step reads its instructions from an editable file. Nothing is hardcoded.

| File | Controls |
|---|---|
| [`prompts/summarize.md`](../prompts/summarize.md) | The 100-150 word summaries and cleaned titles |
| [`prompts/deduplication.md`](../prompts/deduplication.md) | Which articles count as the same story, and which survives |
| [`prompts/newsworthiness.md`](../prompts/newsworthiness.md) | What is worth including |
| [`prompts/tweet_summary.md`](../prompts/tweet_summary.md) | Per-account tweet summaries |
| [`prompts/blog-podcast-summary.md`](../prompts/blog-podcast-summary.md) | Blog post / podcast episode summaries |
| [`prompts/overview.md`](../prompts/overview.md) | How the opening bullets are chosen and written |

---

## Costs

Each module makes one Exa call per configured item — the `*_results` keys change how much each
call returns, not how many calls are made:

- **News** — 1 call per `search_queries` entry
- **Papers** — 1 call per `research_papers.queries` entry
- **Twitter** — 1 call per `twitter_accounts` entry (getxapi, $0.001/call)
- **Blogposts & Podcasts** — plain HTTP feed fetches, no paid API — $0 in retrieval cost

Exa charges **$7 per 1,000 searches** for up to 10 results, and **page text for those first 10
is bundled into that price**. Exa's own generated summary is a *separate* $1 per 1,000 pages,
which is why this pipeline asks for text and writes its own summaries. At 5 results per query
you stay inside the bundle and pay nothing for content.

Two things to watch: raising any `*_results` key **above 10** adds $1 per 1,000 for each extra
result and leaves the bundled-contents window; and `news_results` also drives LLM cost, since
every news result fetched is summarized and then enters both filter prompts.

Verify current rates at [exa.ai/pricing](https://exa.ai/pricing).

---

## Debugging a run

Every run writes `logs/{run_id}.json` — the exact list of items sent to each pass and the raw
decision that came back, plus the summarization coverage stats. Useful for checking *why* a
specific article was kept or dropped, not just how many were.

Run history is in `data/state.db`:

```bash
sqlite3 data/state.db "SELECT run_id, status, article_count, cost_usd FROM runs ORDER BY started_at DESC LIMIT 10;"
```
