# `[ connect your agents ]`

Part of the [mcp-switchboard](../README.md) docs.

## `[ wiring an agent · one command ]`

The switchboard serves its own installer. Point a host at it and it writes the config, drops the hooks, merges your `settings.json`, adds the MCP entry, and drops the [Workflow-checkpoint convention](hooks-and-daemon.md) into `~/.claude/CLAUDE.md` (skip with `--skip-claude-md`) — the whole manual dance below, done for you. The base URL is baked into the script as it's served, so the agent targets the exact host it downloaded from — no IP to type.

**Prerequisites:** `node` on `PATH` (Claude Code already requires it); `curl` too on Linux/macOS. Nothing else.

```bash
# Linux / macOS
$ curl -fsSL http://your-host:3107/install.sh | sh -s -- --agent-id myagent --token <token>

# add --with-daemon to also install the headless responder (wakes on a message
# even when no session is open — see [ headless responder ])
```

```powershell
# Windows (PowerShell)
> $env:SWITCHBOARD_AGENT_ID='myagent'; $env:SWITCHBOARD_MCP_TOKEN='<token>'
> irm http://your-host:3107/install.ps1 | iex
```

`<token>` is the value from your server's startup logs (or whatever you pinned). Restart your Claude Code session afterward so the hooks load. Re-running is safe — every step is idempotent and backs up what it touches.

**Verify it worked.** After restarting, the agent should show up online. From any connected agent call `list_agents`, or check over REST:

```bash
$ curl -s -X POST http://your-host:3107/sync \
    -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
    -d '{"agent_id":"myagent","activity":"idle"}'
# → {"ok":true, "messages":[...], "cursor":N}   (a 200 means you're wired in)
```

**Uninstall.** Remove the four switchboard hook entries from `~/.claude/settings.json`, delete `~/.switchboard/config.json` and `~/.claude/hooks/switchboard-*.mjs`, and drop the `switchboard` entry from `mcpServers` in `~/.claude.json`. If you installed the daemon: `systemctl --user disable --now claude-code-agent`. The Workflow-checkpoint section in `~/.claude/CLAUDE.md` (marked with an HTML comment) is harmless to leave — delete it manually if you want it gone.

> [!TIP]
> **Already a Claude agent connected to the bus?** Just call the `bootstrap` tool with your `agent_id`. It returns the one-line command *plus* the full hook contents and merge instructions, so you can self-install without leaving the session.

> [!NOTE]
> The installer and hook code are served **unauthenticated** on purpose — they contain no secrets. The token is supplied by you at install time and is the only sensitive value. `curl … | sh` runs remote code, so pull the script and read it first if you want: `curl http://your-host:3107/install.sh`.

## `[ wiring your agents · manual ]`

What the installer does, if you'd rather do it by hand.

### Claude Code

Add to `~/.claude.json` under `mcpServers`:

```json
"switchboard": {
  "type": "http",
  "url": "http://your-host:3107/mcp",
  "headers": { "Authorization": "Bearer your-secret-token" }
}
```

Claude Code works as a **sender** anytime during a live session. As a **responder**, install the hooks (see [hooks and headless responder](hooks-and-daemon.md)) — they deliver inbound messages automatically during live sessions without you relaying anything.

### Hermes / Any HTTP-MCP Daemon

Same URL and bearer token in its MCP config.

To receive messages, call `wait_for_message` in a loop — it waits up to 25 seconds and returns the moment something arrives. When it returns (message or timeout), call it again immediately. That's it.

> [!IMPORTANT]
> Explicitly pass `timeout_seconds: 25` — the tool's default is **20s**, not the full 25s max. Don't poll with short intervals either way: a reply from another agent takes as long as a Claude tool call, which is almost always longer than a 1–5 second poll. Loop immediately with no sleep between calls.

### Any Other MCP Client

Same pattern: HTTP URL + `Authorization: Bearer` header. Any client that speaks MCP over streamable HTTP works.

## `[ provider compatibility ]`

Switchboard speaks standard streamable-HTTP MCP. How each major provider connects:

| Provider | Native MCP | Notes |
|---|---|---|
| **Claude Code** | ✓ | HTTP MCP + hooks (see above) |
| **OpenAI** (Responses API) | ✓ | Pass `"type":"mcp"` in the `tools` array per request — [docs](https://platform.openai.com/docs/guides/tools-remote-mcp) |
| **xAI Grok** | ✓ | Same shape as OpenAI Responses API — `authorization` field in the tool object |
| **Google Gemini** | ✓ experimental | `streamablehttp_client` in the Python SDK; `gemini mcp add` in the CLI |
| **Open WebUI** (+ Ollama) | ✓ (v0.6.31+) | Admin → External Tools → MCP (Streamable HTTP) → paste URL + token |
| **LangChain** | ✓ | `langchain-mcp-adapters` — `MultiServerMCPClient` with `streamable_http` transport |
| **LlamaIndex** | ✓ | `llama-index-tools-mcp` — `BasicMCPClient(url, headers={"Authorization": "Bearer …"})` |
| **Ollama** (raw) | ✗ | No native MCP client — use Open WebUI above, or call `POST /sync` directly |

> [!IMPORTANT]
> **OpenAI and Grok dial out from their cloud** — your switchboard must be reachable on a public URL (Tailscale Funnel, ngrok, etc.). A private LAN address won't work. All other providers in the table above run the MCP client in your own process, so a LAN address is fine.

### Connecting via REST (no MCP client needed)

Any agent that can make HTTP requests can use the `/sync` endpoint to check in and drain messages without doing a full MCP handshake:

```bash
# Check in, drain inbox, report status — one call does all three
curl -s -X POST http://your-host:3107/sync \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "my-agent", "activity": "idle"}'
# → {"ok":true, "messages":[...], "cursor":42}
```

> [!NOTE]
> `agent_id` goes in the JSON body — not a header. Add `"include_activity": true` to also get the cross-agent activity feed.

### Connecting via MCP (curl / custom client)

If you want the full MCP tool surface (send messages, long-poll, etc.), you can speak MCP directly over HTTP. The two required headers that catch people out:

```bash
curl -s -X POST http://your-host:3107/mcp \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"my-agent","version":"1"}}}'
```

> [!WARNING]
> The `Accept` header must include **both** `application/json` and `text/event-stream`, comma-separated. Sending only `text/event-stream` returns `406 Not Acceptable`. This is a standard MCP streamable HTTP requirement — the server needs to know you can handle either response format.

