# Project instructions

## Changelog

Whenever a structural/pipeline feature is added or changed, add an entry to `Changelog.md`.
Do not log config-only changes (search queries, Twitter accounts, model names, etc.) — only
things a user of the pipeline would consider a new capability or behavior change.

Write entries with as little technical detail as possible:
- Keep each entry to a single short paragraph. If it needs more than that, it is carrying
  detail that belongs in the code or the README, not here
- No code, file, or variable names — describe what changed in plain terms
- Explain *why* it mattered, not just what changed
- Say what impact was observed (before vs. after), if known
- Group related changes under one heading rather than listing them separately
- If something was tried and didn't work, say so, and say what was done instead
- If an investigation or analysis informed a decision, mention what was checked and what it showed

New entries go at the top, under a `## YYYY-MM-DD` heading for today's date.
