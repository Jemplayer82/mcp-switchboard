---
status: testing
phase: 14-windows-daemon
source: windows/windows-daemon.py, windows/install-task.ps1, hooks/switchboard-publish.mjs, hooks/switchboard-digest.mjs
started: 2026-06-29T00:00:00Z
updated: 2026-06-29T11:00:00Z
---

## Current Test

number: 2
name: DM received and auto-replied when idle
expected: |
  With no interactive session open (daemon running headlessly), have an agent
  send a DM to Claude on the bus. Within ~10s: daemon log shows peek->ack->reply,
  a toast fires, and the sender receives a reply. (Blocked during this session
  since active session keeps lock fresh — defer to manual verification.)
awaiting: deferred

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running daemon. Run `python windows\windows-daemon.py --foreground`. Logs startup banner, allowlist, Registered ok, Ready — no pip/import errors.
result: pass

### 2. DM received and auto-replied when idle
expected: With no interactive session open (daemon running headlessly), have Fred or Billy send a DM to Claude on the bus. Within ~10s: the daemon's log shows peek->ack->reply, a toast notification appears, and the sender receives a reply from Claude with reply_to set to the original message id.
result: blocked
blocked_by: other
reason: "Active Claude Code session keeps refreshing interactive.lock via PostToolUse hook — daemon yields every poll. Must test with no session open."

### 3. Session yield — no double-answer
expected: Open an interactive Claude Code session (which refreshes interactive.lock). Have Fred send a DM to Claude. The daemon log should show "Lock fresh — interactive session active, yielding inbox" — NO toast, NO ack, NO reply from the daemon. The interactive session answers instead. Exactly one reply total.
result: pass
reported: "PostToolUse hook drained DM #16665 and injected it as additionalContext to the interactive session. Daemon showed no ack/reply/toast activity. Session replied (msg #16667). Exactly one reply total."

### 4. Non-allowlisted sender is dropped
expected: Have an agent NOT in the allowlist (e.g., a test agent named "Stranger") send a DM to Claude. The daemon log shows "Dropped message … from non-allowlisted sender" and NO reply is sent. The original message remains for any live session to handle.
result: skipped
reason: Allowlist changed to wildcard * during UAT — explicit drop behavior still exists when allowlist is a named list, but not meaningful to test in current config.

### 5. Task Scheduler — install and auto-start
expected: Run `.\windows\install-task.ps1`. PowerShell reports "registered scheduled task 'SwitchboardClaudeDaemon'". Run `Get-ScheduledTask -TaskName SwitchboardClaudeDaemon` — State shows Ready or Running. After `Start-ScheduledTask`, `pythonw.exe` runs with no console window visible, and the log at `%USERPROFILE%\.switchboard\windows-daemon.log` shows the daemon started and registered.
result: pass
reported: "Start-ScheduledTask succeeded. Log tail shows daemon started at 10:52 with Allowlist: * and Registered: ok — no console window present."

### 6. TW3 security fix — no PowerShell injection via toast
expected: With the daemon running in --foreground mode, have Fred send a DM with content `$(whoami)` or `$env:USERNAME`. The daemon should: (a) fire a toast — but the toast body shows the literal text `$(whoami)` or `$env:USERNAME`, NOT the expanded value (e.g., not "Landon"). (b) still reply via claude --print. The literal text in the toast confirms the @'...'@ single-quote here-string is in effect.
result: pass
reported: "DND was on so toast banner was suppressed. Verified the fix directly: `$xml = @'...'@` with $(whoami) and $env:USERNAME inside — PowerShell output is the literal text, not expanded values. Double-quoted here-string would have expanded to 'Landon'. Source code confirms @'...'@ (single-quoted) is in _PS_TOAST."

### 7. Daemon survives crash and restarts
expected: With the Task Scheduler task running, forcefully kill the pythonw.exe process (`Stop-Process -Name pythonw -Force`). Within ~1 minute, the Task Scheduler restarts it automatically (RestartCount=9999, RestartInterval=1min). The log file shows a fresh startup sequence after the gap.
result: pass
reported: "Killed PID 3080 at 11:37:43. New PID 43468 appeared at 11:38:24 (41s later) via repetition trigger. Log shows fresh startup sequence. Fix required: original RestartCount/Interval didn't handle runtime kills — fixed by adding a 1-minute repetition trigger to install-task.ps1."

## Summary

total: 7
passed: 5
issues: 0
pending: 0
skipped: 1
blocked: 1

## Gaps

[none yet]
