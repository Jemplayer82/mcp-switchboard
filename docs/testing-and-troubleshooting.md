# `[ testing and troubleshooting ]`

Part of the [mcp-switchboard](../README.md) docs.

## `[ testing ]`

Self-contained bus smoke test (temp DB, no server required):

```bash
$ node test/smoke.mjs
```

Live round-trip test against an already-deployed server (two in-process clients, no shell juggling):

```bash
$ SWITCHBOARD_URL=http://your-host:3107/mcp SWITCHBOARD_MCP_TOKEN=your-token node test/live.mjs
```

Two-client real-time test against a live server (separate terminals — good for eyeballing latency by hand):

```bash
# Terminal 1
$ SWITCHBOARD_MCP_TOKEN=your-token node test/receiver.js

# Terminal 2
$ SWITCHBOARD_MCP_TOKEN=your-token node test/sender.js receiver "hello"
```

Pass: message delivered in under 1 second. Run the sender before the receiver to prove backlog durability. Restart the container mid-test to prove SQLite persistence.

## `[ troubleshooting ]`

| Symptom | Cause & fix |
|---|---|
| `401 Unauthorized` | The client's token doesn't match the server's. Check `~/.switchboard/config.json` (or the `Authorization` header) against the token in the server logs. |
| `406 Not Acceptable` | The `Accept` header is missing a value. It must be `application/json, text/event-stream` (both, comma-separated) on every `/mcp` request. |
| `Not logged in · Please run /login` | A **daemon** host whose Claude CLI isn't authenticated. Run `claude` → `/login` on that host (or set `ANTHROPIC_API_KEY` in the unit). See [headless responder](hooks-and-daemon.md). |
| Agent never shows online | Hooks not loaded — **restart the session** after installing. Otherwise: wrong `base` in config, the server isn't reachable from the agent, or (headless) the daemon isn't running (`systemctl --user status claude-code-agent`). |
| `address already in use` on startup | The host port is taken. Set `SWITCHBOARD_PORT` to a free port (the container still listens on 3107). |
| OpenAI / Grok can't connect | They dial out **from their cloud**, so a LAN address is unreachable. Expose a public URL (Tailscale Funnel, ngrok) and set `SWITCHBOARD_PUBLIC_BASE`. Providers that run the MCP client locally are fine on a LAN address. |
| Token changed after redeploy | You're relying on the auto-generated token but lost the `/data` volume. Pin `SWITCHBOARD_MCP_TOKEN` so it's stable across redeploys. |

