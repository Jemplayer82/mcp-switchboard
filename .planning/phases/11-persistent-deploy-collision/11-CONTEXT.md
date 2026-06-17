# Phase 11: Persistent Deploy + Inbox-Collision Resolution - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run)

<domain>
## Phase Boundary
Ship the responder as a systemd **user** unit on OpenClaw (auto-restart, journald) and
eliminate the inbox-drain collision with the existing cold `claude-code-agent` daemon.
Decision (from Phase 9): OpenClaw's bus id is **Billy** (the cold daemon registers as Billy).
Resolution: **stop + disable `claude-code-agent`** and run the channel responder under the
**Billy** id, so existing senders reach the live full-context responder transparently and
Billy's inbox has exactly one consumer.

Out of scope: hourly context mgmt (Phase 12), security audit (Phase 13).
</domain>

<decisions>
## Implementation Decisions
- Responder id = `Billy`; cold daemon retired (reversible: re-enable `claude-code-agent`).
- Allowlist = `Claude,Fred,Hermes,node24-upgrade,claude-code`.
- Reuse the Phase 10 deploy dir `~/switchboard-channel/` (bridge, harness, .mcp.json, settings, node_modules, trust already in place).
- Unit `claude-channel-agent.service` runs `run-channel-session.py` (Type=simple, Restart=always); harness exits with claude's status → systemd respawns.
</decisions>

<code_context>
## Existing Code Insights
- Model unit on `daemon/claude-code-agent.service` (the cold daemon's unit).
- Bridge + harness verified live in Phase 10.
</code_context>

<specifics>
## Specific Ideas
Cutover: stop+disable claude-code-agent → install+enable+start claude-channel-agent →
confirm active + Billy online + a DM from Claude gets a context-aware reply → restart the
unit and confirm it re-registers and still replies.
</specifics>

<deferred>
## Deferred Ideas
Dropping `--dangerously-load-development-channels` via plugin allowlisting; hourly rotation timer (Phase 12).
</deferred>
