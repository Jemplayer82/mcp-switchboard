# Phase 9: Headless Channel Spike (Go/No-Go Gate) - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run; spec is the approved plan + ROADMAP goal)

<domain>
## Phase Boundary

Empirically confirm — on real hardware, not on paper — that a headless `claude --channels`
session (no TTY, `claude` 2.1.179, OpenClaw Linux) **stays alive while idle** and
**autonomously fires a turn (including a tool call)** when a channel event is pushed, with
zero human interaction. This is a hard go/no-go gate: if it fails, the milestone stops and
the cold `claude-code-agent` daemon is kept untouched.

In scope: a throwaway custom Node channel + a launch harness, run on OpenClaw, pushed
with a synthetic event. Out of scope: the real `switchboard-channel` bus bridge (Phase 10),
deployment as a unit (Phase 11), context management (Phase 12), security (Phase 13).
</domain>

<decisions>
## Implementation Decisions

- Custom **Node** channel (no bun on OpenClaw), launched via `--dangerously-load-development-channels server:webhook` (custom channels are off the Anthropic allowlist).
- Avoid `fakechat`: interactive `/plugin install` + it binds port 8787 (gsd-cloud collision). Use a free port (8799).
- Two-way channel with a `reply` tool so an autonomous turn produces an observable, unambiguous artifact (a logged reply containing a unique token).
- Run on OpenClaw via key-based ssh; trusted-LAN box.
</decisions>

<code_context>
## Existing Code Insights

- Bus client pattern (JSON-RPC over `/mcp`, SSE parse, bearer from `~/.switchboard/config.json`) lives in `daemon/claude-agent-daemon.py` — reused in later phases.
- Channel contract (capability `experimental['claude/channel']`, `notifications/claude/channel`, reply tool) per Claude Code channels-reference docs.
</code_context>

<specifics>
## Specific Ideas

Answer the six sub-questions from the approved plan
(`C:\Users\Landon\.claude\plans\lets-verirfy-1-contex-elegant-pebble.md`):
1. `--channels` functional on 2.1.179?
2. headless no-TTY survival?
3. autonomous turn on push?
4. ≥5 min idle longevity?
5. OAuth scope adequate for channel delivery?
6. compaction viability (or defer to Phase 12)?
</specifics>

<deferred>
## Deferred Ideas

Production launch hardening (auto-confirm the dev-channels dialog vs. allowlisting the
bridge as a plugin), systemd unit, inbox-drain collision — all Phase 11.
</deferred>
