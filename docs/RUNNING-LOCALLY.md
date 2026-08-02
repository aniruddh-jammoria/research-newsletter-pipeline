# Running on your own hardware

Search (Exa) and Twitter (getxapi) are hosted retrieval services with no local equivalent —
those calls always go over the network. Filtering and summarization, on the other hand, are
two **independent** steps, each with its own `provider`/`model`, and either can point at a
cloud API or at your own llama.cpp server, in any combination.

Requires [llama.cpp](https://github.com/ggml-org/llama.cpp) built locally and a GGUF model
downloaded.

---

## Quick start: `mode: local`

The simplest setup — one `mode:` plus a shared set of local keys, applied to both steps:

```yaml
mode: local
model: your-model-label            # cosmetic label — llama-server ignores it, only cost tracking uses it
local_base_url: http://localhost:8080/v1   # optional, this is the default
local_server_exe: D:\llama.cpp\llama-server.exe
local_model_path: D:\llama-models\your-model.gguf
local_server_args:                 # optional, passed straight through to llama-server
  - -c
  - 32768
  - -ngl
  - 999
  - --reasoning-budget
  - 2048
  - --reasoning-budget-message
  - "Time is up. Provide your final answer now."
  - --no-mmap

filter: {}      # inherits everything above
summarize: {}   # also inherits everything above; omit to reuse the filter block
```

[`examples/local.yaml`](../examples/local.yaml) is a complete, real working config — it writes
`filter:`/`summarize:` out in full (the "different providers per step" form below) rather than
using the `mode:` shortcut, but the settings are otherwise exactly this.

### Do not disable reasoning

`--reasoning-budget 0` fully disables a reasoning model's hidden "thinking" tokens. Doing so
caused both the dedup and newsworthiness passes to silently return "keep everything" — a
total collapse of judgement quality that produced no error and was only caught by inspecting
the per-run logs.

A moderate budget restores real judgement. Batch tasks that compare many items against each
other need it far more than single-fact lookups. `--reasoning-budget-message` forces a
graceful wrap-up instead of an abrupt mid-thought cutoff when the budget runs out.

Note that reasoning tokens come out of the same budget as the visible answer, which is why the
pipeline sets generous output caps internally.

---

## Different providers per step

Skip `mode:` and configure `filter`/`summarize` independently when you want them on different
providers or models entirely — for example a cheap cloud model to filter and a local model to
summarize:

```yaml
filter:
  provider: anthropic
  model: claude-haiku-4-5

summarize:   # omit to reuse the filter block as-is
  provider: local
  model: your-local-model
  local_base_url: http://localhost:8081/v1   # different port if it's a different server/model
  local_server_exe: D:\llama.cpp\llama-server.exe
  local_model_path: D:\llama-models\your-model.gguf
```

The two are fully independent — mix freely: filter on cheap cloud Claude Haiku while
summarizing locally, or the reverse, or both local, or both cloud. Anything set explicitly
inside a `filter:`/`summarize:` block overrides whatever `mode:` would otherwise supply.

---

## Server lifecycle

The pipeline auto-manages each local server: on each run it checks the block's
`local_base_url` for a live llama-server. If nothing answers, it launches `local_server_exe`
with `local_model_path` + `local_server_args`, waits for it to come up, and shuts it down when
the run finishes. If a server is already running there — you started one manually, or `filter`
and `summarize` point at the same port — the pipeline leaves it alone rather than
double-starting or stopping something it did not launch.

You only need `local_server_exe` / `local_model_path` for this auto-start behaviour. To manage
the server yourself, start it manually and leave both keys out.

**Known edge:** if a run is killed rather than allowed to exit — a task time limit, a forced
stop, or a reboot — the cleanup hook does not fire and `llama-server` can be left running,
holding VRAM. Check with `Get-Process llama-server` after an interrupted run.

---

## MoE models

For mixture-of-experts models (filenames with an "A#B" active-parameter suffix, e.g. `-A4B-`),
add `--split-mode tensor` to `local_server_args` — noticeably faster on MoE architectures.
Leave it out for dense models, where it can be unstable.

---

## What it costs

Nothing per run, once the hardware is set up. A local model reports $0.00 for both the filter
and summarize steps; only the Exa and getxapi retrieval calls remain, at roughly $0.12 per run
for a 10-query newsletter. See [PIPELINE.md](PIPELINE.md#costs) for the breakdown.

Expect a full local run to take **30-45 minutes** on consumer hardware, dominated by
summarization — one call per article, paper and account.
