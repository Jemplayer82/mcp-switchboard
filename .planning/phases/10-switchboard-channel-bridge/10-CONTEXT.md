# Phase 10: switchboard-channel MCP Bridge - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run; spec = ROADMAP goal + Phase 9 findings)

<domain>
## Phase Boundary

Build the Node ESM stdio MCP server `switchboard-channel.mjs` that bridges the bus into a
live `claude --channels` session: long-poll `wait_for_message` for the responder's agent id,
inject each allowlisted message as a `notifications/claude/channel` event, and expose a `reply`
tool the session calls to answer back on the bus (`send_message`) with `reply_to`/`thread_id`
preserved. Non-allowlisted senders are dropped silently.

In scope: the bridge + its launch wiring, verified via a real bus round-trip under a TEST
agent id. Out of scope: systemd unit + cutover to the `Billy` id (Phase 11), context mgmt
(Phase 12), security audit (Phase 13).
</domain>

<decisions>
## Implementation Decisions
- Bus client = stateless JSON-RPC over `/mcp` + SSE parse (ported from `daemon/claude-agent-daemon.py`); bus transport is sessionless so no MCP handshake.
- Responder agent id from env `SWITCHBOARD_CHANNEL_AGENT_ID` (explicit; avoids the inbox-drain collision); allowlist from env `SWITCHBOARD_ALLOWED_SENDERS` (fail-closed if empty).
- Launch via the Phase 9 recipe: `run-channel-session.py` (sized pty + auto-confirm + held stdin).
- Verify under a throwaway id `Claude-rc-test` (allow only `Claude`) so the cold daemon (`Billy`) is untouched until Phase 11.
</decisions>

<code_context>
## Existing Code Insights
- `daemon/claude-agent-daemon.py` — bus JSON-RPC/SSE client pattern, `~/.switchboard/config.json` (base, token).
- Channel contract (capability, notification method, reply tool) proven working in Phase 9 (`chan-spike/webhook.mjs`).
</code_context>

<specifics>
## Specific Ideas
Round-trip test: from agent `Claude`, `send_message` to `Claude-rc-test` → expect a `reply`
back within ~1-2s (turn latency aside). Spoof test: `send_message` with `from:"EvilAgent"` →
expect silent drop, no reply, bridge stays up.
</specifics>

<deferred>
## Deferred Ideas
Allowlisting the bridge as a plugin to drop `--dangerously-load-development-channels` (Phase 11);
systemd unit + Billy cutover (Phase 11).
</deferred>
