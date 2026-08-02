<#
.SYNOPSIS
    Runs the newsletter pipeline for the weekly scheduled job.

.DESCRIPTION
    Wrapper around `python -m newsletter.pipeline`, invoked by the "Research
    Newsletter" scheduled task. It exists to handle the things Task Scheduler
    does not do for you:

      - sets the working directory to the repo root, because the pipeline
        loads .env relative to the current directory
      - uses the interpreter's full path, because a scheduled task starts with
        a minimal PATH that may not include python.exe
      - forces UTF-8 output, because Python picks the locale codepage when its
        output is redirected, and the pipeline prints non-ASCII characters
      - tees everything to a timestamped log, since a scheduled run has no
        console to watch
      - exits with the pipeline's own exit code, so a failed run shows as a
        failed task rather than a silent success

.PARAMETER Config
    Config file to run, relative to the repo root.

.PARAMETER Test
    Pass --test to the pipeline: writes a markdown preview to test_output/
    instead of generating a PDF and sending it to Telegram.

.EXAMPLE
    .\scripts\run_newsletter.ps1 -Test
    Dry run by hand — no PDF, no Telegram message.
#>
[CmdletBinding()]
param(
    [string] $Config = 'configs\ai-local.yaml',
    [switch] $Test
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -Path $RepoRoot

# Prefer the known interpreter; fall back to PATH only if it has moved.
$Python = 'C:\Users\aniru\AppData\Local\Programs\Python\Python312\python.exe'
if (-not (Test-Path $Python)) {
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $found) {
        throw "python.exe not found at '$Python' and not on PATH."
    }
    $Python = $found.Source
}

$LogDir = Join-Path $RepoRoot 'logs\scheduled'
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir ('{0}.log' -f (Get-Date -Format 'yyyy-MM-dd_HHmm'))

# Python defaults to the locale codepage for redirected output; the pipeline
# prints characters that are not in every codepage, which would crash the run
# on encoding rather than anything to do with the newsletter itself.
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED  = '1'

$pipelineArgs = @('-m', 'newsletter.pipeline', $Config)
if ($Test) { $pipelineArgs += '--test' }

("=== Research Newsletter - started {0} ===" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) | Tee-Object -FilePath $LogFile
"Repo:   $RepoRoot"          | Tee-Object -FilePath $LogFile -Append
"Python: $Python"            | Tee-Object -FilePath $LogFile -Append
"Config: $Config"            | Tee-Object -FilePath $LogFile -Append
"Args:   $($pipelineArgs -join ' ')" | Tee-Object -FilePath $LogFile -Append
""                           | Tee-Object -FilePath $LogFile -Append

# Windows PowerShell turns native stderr into ErrorRecords, which would become
# terminating errors under $ErrorActionPreference = 'Stop' the moment Python
# writes a warning. Relax it for the call itself and rely on the exit code.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $Python @pipelineArgs 2>&1 | Tee-Object -FilePath $LogFile -Append
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

""                           | Tee-Object -FilePath $LogFile -Append
("=== Finished {0} - exit code {1} ===" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $exitCode) | Tee-Object -FilePath $LogFile -Append

# Keep the log directory from growing forever.
Get-ChildItem -Path $LogDir -Filter '*.log' |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-90) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

exit $exitCode
