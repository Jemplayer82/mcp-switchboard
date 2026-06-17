---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Headless Full-Context Channel Responder
status: Awaiting next milestone
stopped_at: v1.2 complete — Billy live as the full-context bus responder
last_updated: "2026-06-17T04:13:16.416Z"
last_activity: 2026-06-17 — Milestone v1.2 completed and archived
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 5
  completed_plans: 5
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-16)

**Core value:** Two agents exchange a message in real time (sub-second while a recipient is actively waiting) with zero per-agent custom plumbing — wiring a new agent is one HTTP MCP config line.
**Current focus:** ✅ v1.2 COMPLETE — all 5 phases done. Billy is the live full-context bus responder.

## Current Position

Phase: Milestone v1.2 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-06-17 — Milestone v1.2 completed and archived

### Milestone v1.0 — Built & verified

- Phase 1-2 (Bus Core + Presence/Wake/Awareness): server.js/bus.js/tools.js/schema.sql — 12 MCP tools + REST /status,/activity. Smoke test green (<1s delivery, drain, no-redelivery, channels, instruction→result, presence, activity).
- Phase 3 (Ship): ghcr.io/jemplayer82/mcp-agentbus:latest via CI; deployed as STANDALONE Portainer stack (deviation from "merge into mcp-shared" — chosen for zero blast radius on the 9-service production stack; reversible). Live /healthz ok, durability proven across container recreate.
- Phase 4 (Wire + hooks): Claude Code .claude.json entry added (backup at C:/tmp/claude.json.backup-*); awareness hooks merged into ~/.claude/settings.json (backup at C:/tmp/claude-settings.backup-*); ~/.agentbus/config.json written. Hooks tested live. **Takes effect on next Claude Code restart.**
- Port note: 3107 was taken by mcp-home-assistant → host 3108.
- Token: C:/tmp/agentbus-token.txt (also in .claude.json + ~/.agentbus/config.json). NOT committed.
- Phase 5 (Verify): Blocked on Hermes wiring (OpenClaw host not accessible). VERIFY-02 deferred.

### Milestone v1.1 — Deferred (unstarted)

- Phase 6: Gateway Stand-Up + Switchboard Redeploy — NOT STARTED (deferred)
- Phase 7: Playwright Scraper Behind Gateway — NOT STARTED (deferred)
- Phase 8: Client Rewire + End-to-End Verify — NOT STARTED (deferred)

### Milestone v1.2 — In planning

- Phase 9: Headless Channel Spike (Go/No-Go Gate) — ✅ COMPLETE (PASSED, GO)
- Phase 10: switchboard-channel MCP Bridge — ✅ COMPLETE (verified live)
- Phase 11: Persistent Deploy + Inbox-Collision Resolution — ✅ COMPLETE (Billy live; cold daemon retired)
- Phase 12: Hourly Context Management — ✅ COMPLETE (in-session /compact, continuity preserved)
- Phase 13: Security Audit + End-to-End Verify — ✅ COMPLETE (M1/M2/M3 live; injection refused; real-Fred E2E)

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- One centralized HTTP MCP server = the bus (no broker) — shared state is automatic
- Long-poll `wait_for_message` is the real-time primitive (MCP can't push to an idle LLM)
- Stateless per-request transport + module-level singleton bus (matches existing repos)
- `better-sqlite3` over experimental `node:sqlite` — synchronous, single-writer-safe with WAL
- LAN addressing `192.168.7.50:3108` (3107 was taken), single shared `AGENTBUS_MCP_TOKEN`
- (v1.1) Supergateway on `:8000` fronts all MCP servers — single host:port; new backends mount without new ports
- (v1.1) Scraper = wrap official `@playwright/mcp`, not a bespoke build — upstream-maintained, browsers baked into image
- (v1.1 open) Path-routing mechanism on `:8000` (one supergateway per backend behind nginx vs. path-router) — to be resolved in Phase 6 plan step
- (v1.2) Bridge code in Node (no bun) on OpenClaw; custom channel MCP requires `--dangerously-load-development-channels`
- (v1.2) Headless responder MUST run interactive in a sized pty (Python `openpty`+`TIOCSWINSZ`); channels do NOT fire turns under `-p`/stream-json. Launch via `run-channel-session.py`; auto-confirm the dev-channels dialog; pre-accept workspace trust.
- (v1.2 RESOLVED) Inbox-drain collision: OpenClaw's bus id is **Billy** (cold `claude-code-agent` daemon = Billy). Plan: **retire `claude-code-agent` and run the channel responder under `Billy`** so existing senders reach the live responder transparently (Phase 11).
- (v1.2) Cost: every channel turn is a full Opus-4.8 turn (~$0.10+/turn) — real per-message responder cost; address in Phase 13/ops.

### Pending Todos

- Resolve open decision: how exactly does path routing work on `:8000`? One supergateway instance per backend behind `mcp-nginx-proxy`, or a dedicated path-router? Decide before Phase 6 implementation.
- Phase 6: identify and update all stale `agentbus` / id 63 / `:3108` references before redeployment.
- Phase 9: run spike Phases A → B → C per approved plan (`lets-verirfy-1-contex-elegant-pebble.md`) before writing any bridge code.
- Phase 11 (pre-work): decide dedicated agent id vs. retire cold daemon — both paths are valid; make the call before implementing the systemd unit.

### Blockers/Concerns

- **[Phase 9 — GATE ✅ CLEARED] The headless spike PASSED** (2026-06-16). A no-TTY `claude --channels` session stayed alive idle and autonomously fired turns on push (PONG-7F3A9 ~9s; LONGEVITY-Q9Z after 6.5min idle ~4s). GO — Phases 10–13 proceed.
- **[Phase 5 — HELD] Hermes wiring is the user's step.** Hermes runs on the OpenClaw host (192.168.1.19); SSH not accessible to Claude. To wire: add HTTP MCP entry `agentbus` → `http://192.168.7.50:3108/mcp` with bearer token from `C:/tmp/agentbus-token.txt`. Once wired, VERIFY-02 can run. This may be superseded by v1.1 gateway rewire (CONN-04).
- [Phase 2/4] `wake_url` push depends on OpenClaw exposing a reachable run-trigger endpoint. Falls back to persistent long-poll loop if not available.
- [Phase 4] Claude Code cannot be webhook-woken — no `wake_url` for Claude; async path is turn-boundary hooks only.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Verification | VERIFY-02 (Hermes round-trip) | Blocked on Hermes wiring — user step | Phase 5 |

## Session Continuity

Last session: 2026-06-16
Stopped at: v1.2 SHIPPED — all 5 phases complete, audited (PASSED), archived, tagged
Resume file: None
Next action: `/gsd-new-milestone` to start the next milestone (e.g. v2 per-agent tokens / dashboard, or resume deferred v1.1 gateway+scraper)

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
