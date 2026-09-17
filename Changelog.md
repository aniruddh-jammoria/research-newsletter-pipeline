# Changelog

A running record of what changed, why it mattered, and what impact it had.
Config changes (search queries, Twitter accounts) are not logged here.

Writing style for new entries (see also `CLAUDE.md`): as little technical detail as
possible — no code, file, or variable names. Describe what was done, why it mattered, and what impact was observed. Group related changes under one heading. If something was tried and failed, or an investigation/analysis shaped a decision, say so.

Keep each entry to a single short paragraph. If it needs more than that, it is
carrying detail that belongs in the code or the README, not here.

---

## 2026-09-16

### Captured the local model server's own output instead of discarding it
A manual run this week got partway through summarizing articles, then the local model server stopped responding entirely and every remaining step failed until the whole run gave up. There was no way to tell why: the server's own output was being thrown away rather than kept anywhere. It now writes what it prints to a file next to the other run data, so the next time it dies mid-run there's an actual error message to look at instead of a guess. The slowdown that preceded the failure also matched a pattern from the week before, so GPU memory pressure from other running programs is suspected but not yet confirmed as the cause.

### Stopped paying twice for search results after a failed run
Every retry after a mid-run failure was re-running the paid article and paper searches from scratch, even though the local model — the part that had actually failed — costs nothing to rerun. Search results are now kept for the rest of the day they were fetched, so a same-day retry reuses what was already paid for instead of searching again. A retry with different search terms still searches fresh, and the next day's run always starts clean.

## 2026-09-15

### Stopped a stuck run from tying up the machine for hours
Last week's scheduled run hit a slowdown during summarization and never finished — after three hours it was killed outright, well past how long a normal run takes, and because of how it was killed, the local model server it had started was left running in the background afterward, doing nothing but holding onto GPU memory. The scheduled run is now cut off much sooner (90 minutes instead of three hours) so a stuck run fails fast rather than grinding for most of a workday, and it now also checks for and cleans up a leftover model server from a prior run before starting a new one, so an abrupt kill doesn't leave anything running indefinitely.

## 2026-09-07

### Made the deduplication step tolerant of a miscounted response
This week's scheduled run got through search and summarization but then failed completely during deduplication: the model was asked for one keep/drop decision per article and, on its second attempt, still returned one too many. That mismatch aborted the whole run, so no newsletter was produced at all that day. Now, if a retry still comes back with more decisions than articles, the extra ones are simply dropped rather than treated as a fatal error, so a run doesn't lose everything over an off-by-one from the model.

## 2026-08-17

### Extended the local model startup timeout
This week's scheduled run failed before doing any work because the local model server wasn't ready within the one-minute window the pipeline allowed for it to start, aborting the whole run. The three prior weekly runs had all started in time, so this looks like an occasional timing margin issue rather than a broken setup. The window was extended to three minutes so a slower-than-usual load doesn't sink an entire run.

## 2026-08-02

### Added a Blogposts & Podcasts section
The newsletter now has a fourth section, Blogposts & Podcasts, between News and Research Papers — a curated list of outlets, configured by name and feed address, with anything published in the past week condensed to a single 30-word-or-fewer sentence each. Sources must be a direct RSS/Atom feed rather than any web page: guessing or scraping a feed turned out unreliable, so only known-good feeds, verified by hand, are used. Several requested podcasts have no public feed at all — their Spotify listening pages don't expose one — so those are left out until a working feed is found for them.

## 2026-07-26

### Send the week's summary to Telegram alongside the PDF
The delivery message was just a filename and a count, so seeing what was in the newsletter meant opening the attachment — on a phone, several taps for something that fits on one screen. The opening bullets are now included with the file. Telegram caps the text attached to a file at around a thousand characters, which five full-length bullets can exceed, so when they do not fit they arrive as a separate message immediately after rather than being cut short or silently dropped.

### Stopped an empty notes file from being fed to the filters as instructions
The file for accumulating learnings across runs ships as a template of empty section headings, and all of it — headings, plus a preamble describing the file itself and referencing a tool that no longer exists — was being appended to two prompts on every run under the label "additional instructions". Nothing useful, on a step that asks a small local model for careful judgement across dozens of items. An untouched template now counts as empty and nothing is appended; write something under a heading and it takes effect as before. Also removed a leftover report-listing function and an unused style rule, both orphaned when the old web interface was dropped.

### Cleaned up the headlines
Headlines were whatever the web page put in its browser-tab title, so the newsletter printed outlet names and stray punctuation glued onto the end, site navigation trails, identifier codes, and titles the source had already cut short with an ellipsis — and in the worst case a section heading like "1. Introduction" instead of the paper's actual name. One title even contained Korean navigation text that the newsletter's font could not draw, so it printed as boxes. Checking whether this was fixable by requesting a different version of the page showed it was not: the search provider returns the same title whichever form is asked for. But the real title sits in the article text, which the summarizing step already reads in full — so that step now reports the title as the document itself states it, alongside the summary. This is a lookup rather than a rewrite, so nothing is invented, and it costs no extra time. Tested on the worst offenders from a real run, all were corrected; where no usable title comes back the original is kept, so the fallback is exactly the old behaviour.

### Turned the Twitter section into one summary per account
The Twitter section was a raw dump: the few highest-engagement posts per account, printed verbatim and cut off after two sentences, so a substantive thread and a two-word reaction sat side by side and both got truncated mid-thought. Every post an account made in the week is now read together and condensed into a single 50-100 word paragraph covering ideas, announcements and technical observations — so the section reports what someone actually contributed rather than showing fragments of individual posts. Accounts with nothing worth reporting are dropped entirely instead of padded, which on a test run correctly removed an account whose only post that week was a two-word quip. Engagement ranking is gone, since nothing is being selected any more. This adds an LLM call per account, roughly six minutes to a run.

### Added an opening summary, and stopped cutting the summaries short
The newsletter opened straight into an undifferentiated list of nearly thirty articles with nothing to skim, so it now starts with up to five bullets covering what actually mattered that week — written by a separate pass over only the articles that survived filtering, ordered by significance, and combining several articles into one bullet where they are facets of the same story. It is deliberately optional: if that step fails the run carries on and the section is simply left out, since a newsletter without its opening summary is still a complete newsletter. Separately, the printed pages had been trimming every summary to the first few sentences — a holdover from when summaries came from the search engine and ran to unpredictable lengths. Now that they are written to a fixed length, they print in full, which roughly doubled the page count. Like every other step, the wording of the opening summary is controlled by an editable instruction file rather than being baked in.

### Stopped the same paper appearing twice
A test run printed one paper twice: the main preprint archive publishes a single paper at three different addresses, and the "seen this already?" check compared addresses as plain text. Papers skip the duplicate-detection step news goes through, so nothing caught it. Papers are now identified by the paper rather than the address used to reach it — on the run that exposed this, eighteen results become seventeen — and preprint links all point at the abstract page instead of a mix of formats. The same check was added to news, where measuring first showed no such duplicates exist today, so there it is preventative.

### Write our own summaries first, and judge on those
Investigating why duplicate stories kept slipping through found the cause: the search engine's blurbs, which every step relied on, are written to answer whichever search phrase found the article — so two outlets covering one announcement came back described differently, working directly against the step meant to spot they were the same story. Checking the provider's rates showed those blurbs are also a paid add-on, while the plain article text is already included. Summarizing moved to the front: every article and paper is condensed to a short, neutral summary from its own text before any filtering, and that one summary now feeds the duplicate check, the newsworthiness check, and the newsletter — previously it was written only for articles that had already survived, so no decision was ever made on our own writing. This removes about two-fifths of the search bill, ends paywalls and timeouts as a routine failure, and gives the duplicate check shorter, uniform text to work with. Items with no obtainable text are dropped and counted rather than carried forward blank.

### Moved the weekly schedule onto the machine that actually runs it
The weekly run was scheduled through GitHub, whose clock has no notion of daylight saving, so an 8am run would silently become 9am for half the year. It now runs through Windows' own scheduler, which follows the local clock and can additionally wake the machine or catch up on a missed run; GitHub is kept for manual runs. A wrapper makes a scheduled run behave like a hand-typed one — right folder, right interpreter, consistent encoding, a timestamped log, and a failure that actually reports as one. Setup needs administrator rights, and rather than quietly registering a weaker schedule that skips any week you are asleep or logged out, it refuses and explains, with an explicit opt-in for the reduced version. Known edge: a forcibly killed run can leave the local model server holding graphics memory.

### Made "how much to fetch" configurable per section
One setting controlled how many results to fetch, but it only ever reached the news section — papers and Twitter ignored it and used fixed amounts, so asking for more did nothing and said nothing. Each section now has its own setting, since they count different things. The default when the setting was omitted also disagreed with every shipped example, which silently doubled how much news was fetched and therefore the filtering cost; defaults now match the examples.

---

## 2026-07-09

### Added a one-switch way to go fully cloud or fully local
Previously, choosing to run entirely on cloud AI models or entirely on your own hardware meant repeating the same settings in two separate places (once for the "which articles matter" step, once for the "write the summary" step). Added a single setting that sets the default for both at once, so switching between the two modes is now one line instead of a duplicated block. Each step can still be overridden individually if you want a mix — for example, a fast cloud model for the quick decisions and a local model for the longer writing task.

### Added ready-to-use starter templates for each mode
Added two complete, ready-to-copy example setups — one showing the simplest possible cloud setup, one showing a fully offline setup — so a new user can see both side by side and pick a starting point without having to piece it together from scratch. Both were tested end to end before publishing: the cloud version priced out at about a penny for a full run, and the offline version confirmed zero ongoing cost once the one-time hardware setup is done.

### Documented the split between "fetching" and "thinking"
Added a short explanation, with a simple before/after diagram, of which parts of the pipeline always need an internet connection (finding articles and tweets — this can't be avoided, any newsletter tool needs a way to search) versus which parts are optional to run locally (deciding what's worth including, and writing the summaries — the part that would otherwise cost money on every single run). This distinction was already true of how the pipeline worked, it just wasn't written down anywhere before.

---

## 2026-07-07

### Added a debug log for every run
Every run now writes one file recording exactly what was sent to the filtering step and what came back. Previously we could only see a total count of articles kept or dropped, with no way to check *why* a specific article was excluded or whether the process behaved as expected. This log is what made every finding below possible to catch.

### Split filtering into two separate passes: remove duplicates, then judge newsworthiness
One combined pass used to try to do both jobs at once — spot duplicate coverage of the same story, and separately decide what's worth including — and it wasn't reliably doing the duplicate-removal half. We split it into two dedicated passes: first "is this the same story as another one in this batch," then "is this article worth including on its own merits."

We also made the relevance check generic. It used to hard-code a fixed list of AI topics into the rules, which meant the same instructions couldn't be reused for a newsletter on a different subject. Now it simply checks each article against whatever search terms the newsletter is actually configured with.

### Made the filter's response shorter and more reliable
Instead of asking the model to repeat back the full headline and web link for every article it kept or dropped, we now just ask for a short keep/drop answer per article. This cut the size of every response dramatically, and — as a side benefit — fixed a bug where the model would occasionally retype a link slightly wrong when echoing it back, causing an approved article to silently disappear from the newsletter without any error.

### Found and fixed a quality regression on local-model runs
While testing the new debug logs, we discovered that when running on a private/local model, both the duplicate-removal and newsworthiness passes were returning "keep everything" — a silent failure that had gone completely unnoticed before, since only a total count was visible previously.

This traced back to a speed setting: we had turned off the model's "thinking" time entirely to save time, which is what caused the failure. We looked into the tradeoff and confirmed that removing thinking time entirely can make a model underperform on any task that requires comparing many items against each other — sometimes worse than leaving it completely unrestricted. We tested a moderate thinking allowance instead, and quality recovered substantially: the process went from a near-total failure to correctly catching duplicate stories and rejecting low-quality items (ranking listicles, opinion pieces, etc.) that should have been excluded.

### Confirmed the remaining rough edges are not a data problem
After the above fix, a small number of duplicate articles were still slipping through. We checked the actual information the model had been given for these specific cases and found it already had enough detail to tell them apart — full descriptions, not just headlines. The more likely explanation is that comparing around 50 lengthy articles against each other in a single pass is simply a harder task than judging one article at a time, which the model handled well. This is a good candidate for future tuning (e.g. comparing articles in smaller batches) but is a known, minor limitation rather than a bug.

---

## 2026-07-06

### Added the option to run entirely on your own hardware
The two "thinking" steps — deciding which articles matter, and writing summaries — can now run on a model on your own computer instead of paying for a cloud AI service. Search and Twitter fetching still need the cloud (they're not something a local model can do), but the two steps that actually cost money on every run can now be free.

Filtering and summarizing were also split into two separate settings, so they don't have to use the same model. You could, for example, use a fast paid model to decide what's worth including, and a local model to write the summaries — or any other mix. If you don't set up summarizing separately, it just reuses whatever filtering is set to.

Added the option to write your own summaries instead of using the search engine's built-in ones — the pipeline fetches the full article and summarizes it itself. If fetching the full article fails for some reason, it safely falls back to the built-in summary instead of leaving a blank.

The weekly automated run was moved from GitHub's cloud servers to your own machine, since a local model only exists on your own machine and can't be reached from GitHub's servers.

### Automated starting and stopping the local model
Previously you'd have to remember to manually start the local model software before each run. Now the pipeline checks if it's already running, starts it automatically if not, and shuts it down again once the run finishes — so there's nothing to remember. This also works correctly if filtering and summarizing are using two different local models at once.

### Fixed newsletters overwriting each other every week
Each run's output file now includes the date in its name. Previously every run produced the same filename, so each week's newsletter silently replaced the previous one on disk.

---

## 2026-06-21

### Added Research Papers module
Introduced `newsletter/papers.py` as a second content source. Searches academic paper sites via Exa with domain restriction so results stay on-domain. No LLM filter — the domain + query restriction is already targeted enough.

Supported sources: `arxiv.org`, `nature.com`, `openreview.net`. Configurable via `research_papers.queries` and `research_papers.sources` in the newsletter YAML.

### Added Twitter/X module via getxapi
Introduced `newsletter/twitter.py` as a third content source. Fetches real tweets from a configured list of accounts using the [getxapi.com](https://www.getxapi.com) API.

An earlier approach (finding tweets indirectly via web search) was tried first and discarded — coverage was inconsistent and often surfaced sites quoting a tweet rather than the tweet itself. Switching to a dedicated Twitter data provider fixed this.

### Newsletter split into 3 named sections
The PDF now has three explicit sections — News & Analysis, Research Papers, Twitter Highlights. Previously the newsletter was a flat undifferentiated list of articles.

### `--rerun` flag for re-publishing without re-fetching
Every successful run now saves the assembled newsletter. The `--rerun` flag reuses that saved copy to re-render and re-deliver without repeating any searches or LLM calls — useful for testing formatting changes for free.

### Filter reliability fix
The newsworthiness filter occasionally returned a response that failed to parse, usually due to a stray character in an article title. Added an automatic retry: if this happens, the bad response is sent back with a fix request before giving up.

### Newsletter formatting improvements
Trimmed long summaries down to a few sentences, moved article/paper links inline next to the date instead of as a raw web address at the bottom, and reformatted tweets as short bulleted highlights grouped by account.
