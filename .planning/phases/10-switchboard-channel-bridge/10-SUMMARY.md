# Phase 10 Summary: switchboard-channel MCP Bridge

**Result:** ✅ Built and verified against the live bus.

## Delivered
- `channel/switchboard-channel.mjs` — Node ESM stdio MCP channel bridge:
  `claude/channel` capability + `reply` tool; long-polls `wait_for_message` for the responder
  id; injects allowlisted messages as `notifications/claude/channel`; `reply` → bus
  `send_message` with `reply_to`/`thread_id`; sender allowlist (fail-closed). Bus client is the
  stateless JSON-RPC-over-`/mcp` + SSE pattern from `daemon/claude-agent-daemon.py`.
- `channel/run-channel-session.py` — sized-pty launch harness (Phase 9 recipe), exits with the
  claude child status for systemd restart.
- `daemon/claude-channel-agent.service` — systemd user unit (finalized in Phase 11).

## Live verification (OpenClaw, test id `Claude-rc-test`, allowlist=[`Claude`])
| Test | Result |
|------|--------|
| Bridge registers on bus, session shows the channel banner | ✅ `Claude-rc-test` online; "messages from server:switchboard-channel inject directly in this session" |
| Allowlisted DM (msg 4342) → autonomous reply | ✅ reply 4345, `reply_to:4342`, content `BRIDGE-OK-44Q` + correct cwd `/home/landon/switchboard-channel` (real context) |
| `reply` routes back with `reply_to` preserved | ✅ |
| Non-allowlisted `EvilAgent` (msg 4349) | ✅ silently dropped — no reply (18s timeout), bridge stayed alive |
| Allowlisted DM after the drop (msg 4353) | ✅ reply 4355 `STILL-ALIVE-88K` — drop did not break the poll loop |

## Notes for Phase 11
- Test used dedicated id `Claude-rc-test` to avoid touching the cold daemon (`Billy`). Phase 11
  cuts over: retire `claude-code-agent` and run the responder as **Billy** so existing senders
  reach the live responder transparently.
- The `--dangerously-load-development-channels` confirm dialog is auto-handled by the pty
  harness; Phase 11 decides whether to keep that or allowlist the bridge as a plugin.
- Per-turn Opus cost still applies (every injected message = one Opus turn).
