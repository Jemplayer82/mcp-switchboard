# Phase 12: Hourly Context Management - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run)

<domain>
## Phase Boundary
Bound the live responder's context on an hourly cadence so a long-running `Billy` session
doesn't grow unbounded. User's stated intent: "compact every hour." Out of scope: anything
beyond context bounding.
</domain>

<decisions>
## Implementation Decisions
- **In-session `/compact`** (keeps a summary, no downtime) preferred over full rotation, to
  honor "compact". Driven by the pty harness writing `/compact\r` to the session every
  `CHANNEL_COMPACT_INTERVAL_SEC` (default 3600) — same keystroke-injection path already used
  for the dev-channels auto-confirm.
- **Fallback:** if `/compact` injection wedges the session, set the interval to 0 and enable
  `RuntimeMaxSec=3900` in the unit for clean hourly rotation (Restart=always respawns; the
  restart path is already proven clean in Phase 11).
- Verify empirically with a short (90s) interval before locking in 3600.
</decisions>

<code_context>
## Existing Code Insights
- `channel/run-channel-session.py` — pty harness; keystroke injection proven (auto-confirm). Compaction added as a timed `os.write(master, b"/compact\r")`.
- Phase 11 proved `systemctl --user restart` recovers cleanly (rotation fallback is low-risk).
</code_context>

<specifics>
## Specific Ideas
Short-interval test: 90s drop-in → confirm "injected /compact" marker + a compaction indicator
in session.log + Billy still replies to a DM afterward. Then revert to 3600.
</specifics>

<deferred>
## Deferred Ideas
Adaptive compaction (compact on context-pressure rather than a fixed clock) — future.
</deferred>
