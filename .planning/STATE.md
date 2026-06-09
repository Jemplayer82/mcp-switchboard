# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-09)

**Core value:** Two agents exchange a message in real time (sub-second while a recipient is actively waiting) with zero per-agent custom plumbing — wiring a new agent is one HTTP MCP config line.
**Current focus:** Phase 1 — Bus Core

## Current Position

Phase: 1 of 5 (Bus Core)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-06-09 — Roadmap created (5 phases, single milestone, coarse granularity)

Progress: [░░░░░░░░░░] 0%

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
- LAN addressing `192.168.7.50:3107`, single shared `AGENTBUS_MCP_TOKEN`

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2/4] `wake_url` push depends on OpenClaw exposing a reachable run-trigger endpoint. If none exists, Hermes falls back to a persistent long-poll loop. Confirm exact path during the wiring phase.
- [Phase 4] Claude Code cannot be webhook-woken (no inbound endpoint). Its async path is a scheduled/cron headless routine or a live `wait_for_message` loop — do NOT register a `wake_url` for Claude.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-09
Stopped at: Roadmap and STATE created; REQUIREMENTS traceability updated
Resume file: None
