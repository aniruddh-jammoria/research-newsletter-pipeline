# Scheduling the weekly run

The schedule lives in **Windows Task Scheduler**, which runs in local time and follows
daylight saving automatically — 8am stays 8am year-round. GitHub Actions cron is UTC-only
with no DST awareness, so a fixed cron drifts by an hour twice a year in any DST-observing
timezone.

You do not need to schedule `llama-server` separately; the pipeline starts and stops it per
run.

---

## Register the task

From an **elevated** PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-task.ps1
```

That creates a task named *Research Newsletter* running Mondays at 08:00 local. To change
when it runs, re-run with different arguments — it overwrites in place:

```powershell
.\scripts\register-task.ps1 -At 06:30 -DayOfWeek Sunday
```

**Why elevated:** waking the machine for the run, and running whether or not you are logged
on, are both privileged operations. Without them the task can only fire while you are logged
on with the machine awake, and silently skips any week you are not. The script refuses to
register rather than quietly give you the weaker schedule — pass `-WhenLoggedOnOnly` to accept
it deliberately.

---

## What the task runs

[`scripts/run_newsletter.ps1`](../scripts/run_newsletter.ps1), which handles the things a
scheduled context does not give you for free:

- Sets the working directory to the repo root, so `.env` is found
- Pins the Python interpreter path, since a scheduled task starts with a minimal `PATH`
- Forces UTF-8 output, since Python otherwise picks the locale codepage when redirected
- Tees everything to `logs/scheduled/{timestamp}.log`, pruned after 90 days
- Propagates the exit code, so a failed run reports as failed rather than silently succeeding

Task settings: catch up on missed runs, run on battery, 3-hour limit, ignore overlapping
starts, two retries 15 minutes apart.

---

## Useful commands

```powershell
Start-ScheduledTask -TaskName 'Research Newsletter'        # run it now
Get-ScheduledTaskInfo -TaskName 'Research Newsletter'      # last result + next run
Unregister-ScheduledTask -TaskName 'Research Newsletter' -Confirm:$false
```

Dry-run the exact command the task uses, without producing a PDF or sending anything:

```powershell
.\scripts\run_newsletter.ps1 -Test
```

Follow a run in progress from another terminal:

```powershell
Get-Content (Get-ChildItem logs\scheduled\*.log | Sort-Object LastWriteTime -Desc | Select -First 1).FullName -Wait -Tail 20
```

---

## Alternative: self-hosted GitHub Actions runner

[`.github/workflows/newsletter.yml`](../.github/workflows/newsletter.yml) is kept for manual
runs (`workflow_dispatch`) and is configured for `runs-on: [self-hosted, Windows]`. Its
schedule was removed in favour of Task Scheduler. To drive it from Actions instead:

1. Repo → **Settings → Actions → Runners → New self-hosted runner**
2. Follow the download and configure commands GitHub shows you
3. Install as a Windows service: `.\svc.cmd install` then `.\svc.cmd start`
4. Add all six keys from `.env` as repository secrets, and restore a `schedule:` trigger

Note that GitHub disables scheduled workflows after 60 days of repo inactivity, and the
machine still has to be on and awake either way.

Cloud providers work from either path — `provider` is set per `filter`/`summarize` block, so
you can run some newsletters (or one step of one newsletter) locally and others on Claude or
GPT.
