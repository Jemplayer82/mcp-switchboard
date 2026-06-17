# Phase 10 Plan: switchboard-channel MCP Bridge

**Requirements:** RESP-02 (long-poll → inject), RESP-03 (reply tool → send_message), RESP-04 (allowlist)

## Build
`channel/switchboard-channel.mjs` (Node ESM, MCP stdio):
- capability `experimental['claude/channel']` + `reply` tool.
- on start: register on bus; loop `wait_for_message(agent_id, 25s)`.
- per message: if `from` ∈ allowlist → emit `notifications/claude/channel` with content + meta
  `{from, msg_id, thread_id}`; else log + drop.
- `reply` tool → `send_message{from:agent_id, to, content, reply_to, thread_id, type:result}`.
- config: base/token from `~/.switchboard/config.json`; id from `SWITCHBOARD_CHANNEL_AGENT_ID`;
  allowlist from `SWITCHBOARD_ALLOWED_SENDERS` (fail-closed).

`channel/run-channel-session.py` — sized-pty launch harness (Phase 9 recipe), exits with the
child status for systemd restart.

## Deploy to OpenClaw (test)
`~/switchboard-channel/`: bridge + harness + `.mcp.json` (register `switchboard-channel`) +
`.claude/settings.json` (`enableAllProjectMcpServers`) + `npm i @modelcontextprotocol/sdk`;
pre-accept workspace trust. Launch with `SWITCHBOARD_CHANNEL_AGENT_ID=Claude-rc-test`,
`SWITCHBOARD_ALLOWED_SENDERS=Claude`.

## Verify (real bus round-trip)
1. Bridge starts as stdio MCP server, advertises channel cap + `reply`, long-polls — confirm via session log + bus `list_agents` showing `Claude-rc-test` online. (crit 1)
2. From `Claude`, `send_message` → `Claude-rc-test`; bridge injects <1s; session fires a turn; `reply` routes back to `Claude` with `reply_to`. Confirm reply received. (crit 2, 3)
3. `send_message` `from:"EvilAgent"` → `Claude-rc-test`; confirm silent drop (no reply), bridge alive. (crit 4)

## Pass
All four success criteria observed against the live bus.
