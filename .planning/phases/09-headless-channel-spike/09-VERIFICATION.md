---
phase: 9
status: passed
verified: 2026-06-16
requirements: [VERIFY-04]
gate: go
---

# Phase 9 Verification: Headless Channel Spike (Go/No-Go Gate)

**Verdict: PASSED — GO.** All success criteria met on real hardware (OpenClaw, `claude` 2.1.179).

## Success criteria

- [x] **A `claude --channels` session launched detached (no TTY) starts and registers the channel — not an immediate exit.**
  Evidence: `events.log` `CHANNEL_CONNECTED` + `HTTP listening`; TUI banner "Channels (experimental) messages from server:webhook inject directly in this session". (Required a sized pty + auto-confirm of the dev-channels dialog — see SUMMARY.)
- [x] **Pushing an event to the idle, headless session triggers a visible autonomous turn with zero terminal interaction.**
  Evidence: `PUSH chat_id=1` → `REPLY chat_id=1 text=PONG-7F3A9` (~9s), TUI showed "Calling webhook…".
- [x] **After ≥5 min idle the process is still alive and a subsequent push again triggers an autonomous turn.**
  Evidence: alive at T+5.5min; `PUSH chat_id=2` at 03:39:05 → `REPLY chat_id=2 text=LONGEVITY-Q9Z` at 03:39:09 (~4s, after 6.5 min idle); still alive after.
- [x] **Spike log answers the six sub-questions from the approved plan.**
  Evidence: SUMMARY "Six sub-questions" — channels on 2.1.179 ✓, headless survival ✓, autonomous turn ✓, idle longevity ✓, OAuth scope ✓, compaction deferred to Phase 12 (rotation fallback).

## Gate decision
GO. Proceed to Phase 10 (build `switchboard-channel` bridge). Key constraints for downstream
captured in SUMMARY: interactive-mode-only, sized-pty launch, dev-channels confirm handling,
workspace trust, responder must take over the **Billy** bus id (retire `claude-code-agent`),
per-turn Opus cost.

## Human verification
None required — criteria verified programmatically via event logs and process checks.
