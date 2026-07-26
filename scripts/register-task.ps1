<#
.SYNOPSIS
    Registers (or re-registers) the weekly "Research Newsletter" scheduled task.

.DESCRIPTION
    Creates a Windows Task Scheduler entry that runs scripts\run_newsletter.ps1
    every Monday at 08:00 local time. Local time is deliberate: the machine is
    in a DST-observing timezone, and Task Scheduler follows the clock change
    automatically, so 08:00 stays 08:00 year-round.

    Re-running this script overwrites the existing task, so it doubles as the
    way to change the schedule or the config being run.

.PARAMETER At
    Time of day to run, local time.

.PARAMETER DayOfWeek
    Day to run.

.PARAMETER TaskName
    Name the task appears under in Task Scheduler.

.PARAMETER WhenLoggedOnOnly
    Register a reduced task that does not need administrator rights.

    Running whether or not you are logged on (S4U) and waking the machine for
    the run both require elevation. Without it, the task can only fire while
    you are logged on with the machine awake -- if it is asleep or logged out
    at 08:00 Monday, the run is skipped until the next window. Use this only
    if you cannot run the script elevated.

.EXAMPLE
    .\scripts\register-task.ps1
    Register the default schedule: Mondays at 08:00. Requires elevation.

.EXAMPLE
    .\scripts\register-task.ps1 -At 06:30 -DayOfWeek Sunday
    Move it to Sundays at 06:30.
#>
[CmdletBinding()]
param(
    [string] $At        = '08:00',
    [string] $DayOfWeek = 'Monday',
    [string] $TaskName  = 'Research Newsletter',
    [switch] $WhenLoggedOnOnly
)

$ErrorActionPreference = 'Stop'

$isElevated = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isElevated -and -not $WhenLoggedOnOnly) {
    Write-Error @"
Registering the full task requires an elevated PowerShell.

Waking the machine for the run, and running it whether or not you are logged
on, are both privileged operations. Registering without them would produce a
task that silently skips any Monday you happen to be asleep or logged out --
so this script refuses rather than quietly giving you a weaker schedule.

Either open PowerShell as Administrator and re-run:

    powershell -NoProfile -ExecutionPolicy Bypass -File "$PSCommandPath"

or accept the reduced task explicitly:

    .\scripts\register-task.ps1 -WhenLoggedOnOnly
"@
    exit 1
}

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$RunnerPath = Join-Path $RepoRoot 'scripts\run_newsletter.ps1'

if (-not (Test-Path $RunnerPath)) {
    throw "Runner script not found at '$RunnerPath'."
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $RunnerPath) `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At (Get-Date $At)

$settingsArgs = @{
    StartWhenAvailable       = $true   # catch up if the machine was off at 08:00
    AllowStartIfOnBatteries  = $true
    DontStopIfGoingOnBatteries = $true
    MultipleInstances        = 'IgnoreNew'
    ExecutionTimeLimit       = (New-TimeSpan -Hours 3)
    RestartCount             = 2
    RestartInterval          = (New-TimeSpan -Minutes 15)
}
if (-not $WhenLoggedOnOnly) { $settingsArgs['WakeToRun'] = $true }

$settings = New-ScheduledTaskSettingsSet @settingsArgs

# S4U runs the task whether or not anyone is logged on, without storing a
# password. Outbound network and CUDA both work in that context.
$logonType = if ($WhenLoggedOnOnly) { 'Interactive' } else { 'S4U' }
$principal = New-ScheduledTaskPrincipal `
    -UserId ('{0}\{1}' -f $env:USERDOMAIN, $env:USERNAME) `
    -LogonType $logonType `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName    $TaskName `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -Principal   $principal `
    -Description 'Generates the weekly research newsletter locally and delivers the PDF to Telegram.' `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName

Write-Output "Registered '$TaskName'"
Write-Output "  State:    $($task.State)"
Write-Output "  Schedule: $DayOfWeek at $At local time"
Write-Output "  Next run: $($info.NextRunTime)"
Write-Output "  Mode:     $logonType$(if ($WhenLoggedOnOnly) { ' (reduced - only fires while logged on and awake)' } else { ' (runs logged out; wakes the machine)' })"
Write-Output ""
Write-Output "Run it now:   Start-ScheduledTask -TaskName '$TaskName'"
Write-Output "Remove it:    Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
