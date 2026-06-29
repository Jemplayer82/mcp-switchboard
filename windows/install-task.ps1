# Registers (or removes) the Windows always-on "Claude" switchboard presence daemon
# as an AtLogOn Scheduled Task. The daemon keeps "Claude" visible on the bus, fires
# toast notifications on inbound DMs, and auto-replies headlessly via claude --print
# when no interactive Claude Code session is open.
#
# Usage:
#   .\install-task.ps1                     # install / update the task (idempotent)
#   .\install-task.ps1 -Foreground         # run the daemon interactively for debugging
#   .\install-task.ps1 -Uninstall          # remove the task
#   .\install-task.ps1 -TaskName MyTask    # custom task name (default: SwitchboardClaudeDaemon)
#
# Prerequisites:
#   • Python 3 on PATH  (python.org/downloads)
#   • claude authenticated on this host  (run `claude` once then /login)
#   • ~/.switchboard/config.json present  (written by the main switchboard installer,
#     or copy windows\config.example.json and fill in base + token + agent_id)
#
# After installing, start it immediately with:
#   Start-ScheduledTask -TaskName SwitchboardClaudeDaemon
# It auto-starts at every subsequent login.

param(
    [switch]$Uninstall,
    [switch]$Foreground,
    [string]$TaskName = 'SwitchboardClaudeDaemon'
)

$ErrorActionPreference = 'Stop'

$daemonScript = Join-Path $PSScriptRoot 'windows-daemon.py'

# ── Uninstall ────────────────────────────────────────────────────────────────
if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "-> removed scheduled task '$TaskName'"
    return
}

# ── Python preflight ─────────────────────────────────────────────────────────
$pyCmd  = Get-Command python  -ErrorAction SilentlyContinue
$pywCmd = Get-Command pythonw -ErrorAction SilentlyContinue

if (-not $pyCmd) {
    throw "python not found on PATH. Install Python 3 from https://python.org/downloads/ (make sure to tick 'Add Python to PATH')."
}

$pythonExe  = $pyCmd.Source
$pythonwExe = if ($pywCmd) { $pywCmd.Source } else {
    # Derive pythonw.exe path from python.exe location (same directory)
    Join-Path (Split-Path $pythonExe) 'pythonw.exe'
}

if (-not (Test-Path $pythonwExe)) {
    Write-Warning "pythonw.exe not found at '$pythonwExe'; falling back to python.exe (a console window may flash briefly on login)"
    $pythonwExe = $pythonExe
}

# ── Foreground debug run ──────────────────────────────────────────────────────
if ($Foreground) {
    Write-Host "-> running daemon in foreground (Ctrl+C to stop)"
    & $pythonExe $daemonScript --foreground
    return
}

# ── Register the Scheduled Task ───────────────────────────────────────────────
$action = New-ScheduledTaskAction `
    -Execute $pythonwExe `
    -Argument ('"' + $daemonScript + '"') `
    -WorkingDirectory (Split-Path $daemonScript)

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited   # no admin rights needed

$settings = New-ScheduledTaskSettingsSet `
    -RestartOnFailure `
    -RestartInterval  (New-TimeSpan -Minutes 1) `
    -RestartCount     9999 `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `   # never kill
    -MultipleInstances IgnoreNew `                    # one instance only
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $action `
    -Trigger   $trigger `
    -Principal $principal `
    -Settings  $settings `
    -Force | Out-Null   # -Force makes re-running idempotent

Write-Host ""
Write-Host "-> registered scheduled task '$TaskName'"
Write-Host "   Trigger  : AtLogOn (current user)"
Write-Host "   Exe      : $pythonwExe"
Write-Host "   Script   : $daemonScript"
Write-Host "   Restart  : on failure, every 1 min, unlimited times"
Write-Host "   Logs     : $env:USERPROFILE\.switchboard\windows-daemon.log"
Write-Host ""
Write-Host "   The task starts automatically at your next login."
Write-Host "   To start it right now:"
Write-Host "     Start-ScheduledTask -TaskName $TaskName"
Write-Host ""
Write-Host "   To watch the log:"
Write-Host "     Get-Content `$env:USERPROFILE\.switchboard\windows-daemon.log -Wait"
Write-Host ""
Write-Host "   To uninstall:"
Write-Host "     .\install-task.ps1 -Uninstall"
