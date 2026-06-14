<div align="center">

```
            ·   ·   ·   ·   ·            sonar
          ───────────────────
                  │   · )))
          ─────── ● ───────
                  │
                  ▼                       FATHOM
          ═══════════════════            depth sounder
```

# `$ mcp-switchboard`

**A message bus for AI agents** — spin up one container, point your agents at it,
and they can talk to each other without you in the middle.

![protocol](https://img.shields.io/badge/protocol-MCP-6cd5e6?style=flat-square&labelColor=030d14)
![transport](https://img.shields.io/badge/transport-streamableHttp-6cd5e6?style=flat-square&labelColor=030d14)
![state](https://img.shields.io/badge/state-SQLite-6cd5e6?style=flat-square&labelColor=030d14)
![dependencies](https://img.shields.io/badge/dependencies-none-2ecc71?style=flat-square&labelColor=030d14)
![image](https://img.shields.io/badge/image-ghcr.io-6cd5e6?style=flat-square&labelColor=030d14&logo=docker&logoColor=6cd5e6)
![license](https://img.shields.io/badge/license-AGPL--3.0-6cd5e6?style=flat-square&labelColor=030d14)

</div>

---

## `[ the problem ]`

You're running multiple AI agents. Claude Code handles one task, an Ollama-backed daemon handles another. When they need to share information, *you* are the relay — copying output from one, pasting it into the other, manually keeping them in sync.

That's the human-as-middleman problem. Switchboard eliminates it.

## `[ what it is ]`

A centralized, self-hosted MCP server that acts as a message bus between agents. Any MCP-capable agent — Claude Code, Hermes, Ollama, or anything you add later — connects with one HTTP URL and a bearer token. From there, agents can:

- Send direct messages or broadcast to channels
- Long-poll for real-time message delivery (sub-second)
- Track each other's presence and activity
- Coordinate on tasks without human intervention

One container. One URL. No broker, no Redis, no external dependencies. State lives in SQLite and survives restarts.

## `[ why not a2a ]`

[Google's Agent-to-Agent protocol](https://developers.google.com/agent-to-agent) is the enterprise standard for agent coordination. It's well-designed and well-funded. It also requires implementing Agent Cards, capability discovery schemas, and a new protocol stack — which is the right call if you have an engineering team and an enterprise deployment.

> [!TIP]
> If you want two agents talking to each other *this afternoon*, Switchboard is the answer.

|  | **Switchboard** | **A2A** |
|---|---|---|
| **Setup** | `docker run`, one env var | Agent Cards + capability discovery + protocol implementation |
| **Dependencies** | None (SQLite) | Protocol stack |
| **Best for** | Homelab, small teams, self-hosted | Enterprise, multi-vendor, large scale |
| **Governance** | You | Linux Foundation (Google, Anthropic, OpenAI, Microsoft, AWS) |

## `[ quick start ]`

```bash
$ docker run -d \
    --name switchboard \
    -p 3108:3107 \
    -e SWITCHBOARD_MCP_TOKEN=your-secret-token \
    -v switchboard-data:/data \
    ghcr.io/jemplayer82/mcp-switchboard:latest
```

Health check:

```bash
$ curl -sf http://localhost:3108/healthz
# → {"ok":true}
```

That's it. Point your agents at `http://your-host:3108/mcp`.

## `[ how it works ]`

```
  Claude Code  ──┐
                 ├──► http://your-host:3108/mcp  ──► bus.js (singleton)
  Hermes daemon ─┘         Bearer auth                  ├─ EventEmitter  (sub-second wakeups)
                                                        └─ SQLite        (durable, survives restarts)
```

- **Stateless transport, stateful bus.** Each HTTP request gets its own transport; all handlers close over one shared `bus` singleton. State is shared across all connections automatically.
- **Real-time via long-poll.** `wait_for_message` holds the HTTP response open (up to 25s) and returns the instant a message arrives. Loop it for live receipt.
- **Durable delivery.** Messages and per-agent read cursors live in SQLite. An agent that restarts picks up exactly where it left off — no messages lost, no duplicates.
- **Presence awareness.** Agents call `set_status` to report what they're working on. `get_activity` returns a cross-agent feed so any agent can see what the others are doing.
- **`POST /sync`.** A REST shortcut for hooks and scripts: publishes the agent's current activity AND drains its unread inbox in one round trip. Returns `{ok, messages, cursor}` plus the full activity feed when `include_activity:true`.

## `[ wiring your agents ]`

### Claude Code

Add to `~/.claude.json` under `mcpServers`:

```json
"switchboard": {
  "type": "http",
  "url": "http://your-host:3108/mcp",
  "headers": { "Authorization": "Bearer your-secret-token" }
}
```

Claude Code works as a **sender** anytime during a live session. As a **responder**, install the hooks (see `[ hooks ]` below) — they deliver inbound messages automatically during live sessions without you relaying anything.

### Hermes / Any HTTP-MCP Daemon

Same URL and bearer token in its MCP config. For real-time receipt, either:

- Hold a persistent `wait_for_message` loop (simplest, sub-second latency), or
- Register a `wake_url` in `register_agent` — the bus POSTs to it when a message arrives and no loop is active, triggering the harness to start a run.

> [!IMPORTANT]
> Use a **25-second timeout**, not shorter. Claude's replies land at tool-call boundaries — a single short poll will almost always time out before the reply arrives. Loop immediately after each call with no sleep.

### Any Other MCP Client

Same pattern: HTTP URL + `Authorization: Bearer` header. Any client that speaks MCP over streamable HTTP works.

## `[ tools ]`

| Tool | Purpose |
|---|---|
| `register_agent` | Register or refresh an agent. Idempotent. Pass `wake_url` for daemon webhook-wake. |
| `list_agents` | All agents with online presence flag and current activity. |
| `create_channel` | Create a channel (idempotent). |
| `list_channels` | Channels and member counts. |
| `join_channel` | Join a channel. Cursor initializes at current max — no history flood on join. |
| `send_message` | Send direct (`to`) or to a channel (`channel_id`). Supports `type`, `thread_id`, `reply_to`. |
| `wait_for_message` | Long-poll receive. Returns instantly on backlog or arrival, else after timeout (1–25s). |
| `get_messages` | Non-blocking history or drain. `peek` to read without advancing cursor. |
| `ack` | Explicitly advance read cursor. For peek-then-act flows. |
| `heartbeat` | Refresh presence between polls. |
| `set_status` | Report what this agent is currently working on. |
| `get_activity` | Cross-agent activity feed + presence snapshot. |

## `[ hooks — inbound delivery for claude code ]`

The `hooks/` directory contains Node ESM scripts that wire Claude Code into the switchboard automatically. Install them in `~/.claude/settings.json`. They are fire-and-forget with a 1.5s timeout — they never block your session.

### `switchboard-publish.mjs` — PostToolUse + Stop

Fires on every tool call and at the end of each turn.

- **PostToolUse:** calls `POST /sync`, publishes the current activity, and injects any arriving DMs as `additionalContext` so Claude sees them before its next action in the same turn.
- **Stop (first time):** drains the DM inbox; if messages are pending, returns `{"decision":"block"}` to keep the turn alive so Claude can reply before going idle.
- **Stop (guarded):** if `stop_hook_active:true` is in the payload, exits silently — prevents infinite loops. The platform enforces a hard cap of 8 blocks per turn regardless.

### `switchboard-digest.mjs` — SessionStart + UserPromptSubmit

Fires at session start and before every user prompt. Calls `POST /sync` with `include_activity:true` to drain any messages that arrived during idle time and surface the cross-agent activity feed as context.

### Configuration

Create `~/.switchboard/config.json`:

```json
{
  "base": "http://your-host:3108",
  "token": "your-secret-token",
  "agent_id": "claude-code",
  "inbound": {
    "deliver": true,
    "block_on_stop": true
  }
}
```

Set `block_on_stop: false` to disable the Stop-hook blocking without redeploying. Set `deliver: false` to disable mid-turn injection entirely.

## `[ deploy · docker compose ]`

```yaml
services:
  switchboard:
    image: ghcr.io/jemplayer82/mcp-switchboard:latest
    ports:
      - "3108:3107"
    environment:
      - SWITCHBOARD_MCP_TOKEN=${SWITCHBOARD_MCP_TOKEN}
    volumes:
      - switchboard-data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:3107/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  switchboard-data:
```

> [!IMPORTANT]
> Set `SWITCHBOARD_MCP_TOKEN` in your environment or `.env` file. **Never commit it.**

## `[ portainer deployment ]`

The prebuilt image is published to `ghcr.io/jemplayer82/mcp-switchboard:latest` by GitHub Actions on every push to `main`. Deploy via Portainer as a standalone stack using the compose file above. Set `SWITCHBOARD_MCP_TOKEN` in the Portainer stack environment — not in the committed compose file.

After a fresh CI build, force-pull the latest image before redeploying:

```bash
$ docker compose pull && docker compose up -d
```

> [!WARNING]
> Portainer's `GET /api/stacks/<id>` returns `Env: []` (secrets redacted). If you PUT that empty array back, it **wipes** the environment variables. Always re-supply the full `Env` array on any stack update.

## `[ testing ]`

Self-contained bus smoke test (temp DB, no server required):

```bash
$ node test/smoke.mjs
```

Hook contract test (spins up a local server, fires synthetic hook payloads):

```bash
$ bash test/hook_contract_test.sh
```

Two-client real-time test against a live server:

```bash
# Terminal 1
$ SWITCHBOARD_MCP_TOKEN=your-token node test/receiver.js

# Terminal 2
$ SWITCHBOARD_MCP_TOKEN=your-token node test/sender.js receiver "hello"
```

Pass: message delivered in under 1 second. Run the sender before the receiver to prove backlog durability. Restart the container mid-test to prove SQLite persistence.

## `[ honest limitations ]`

> [!WARNING]
> **One replica only.** The in-process EventEmitter and single-writer SQLite assume one container. Do not scale horizontally against the same volume.

- **Shared token.** All agents share one `SWITCHBOARD_MCP_TOKEN` and self-assert their `agent_id`. Fine for a trusted home network. Per-agent tokens are a straightforward future upgrade.
- **Closed sessions can't be woken.** The hooks deliver inbound messages to any *running* Claude Code session automatically. But if Claude Code isn't open at all, messages queue in SQLite and drain the moment a session starts. For always-on coverage, run a persistent session or a scheduled `claude -p` responder. Daemons like Hermes handle this with a long-poll loop or `wake_url`.
- **MCP can't start an LLM.** The bus can wake a *harness* (via `wake_url`) but only if the harness exposes an HTTP trigger endpoint. It cannot spin up a model from nothing.

## `[ architecture notes ]`

Switchboard is intentionally simple:

- **No broker.** An in-process `EventEmitter` handles real-time wakeups. No Redis, no Kafka, no external dependencies.
- **SQLite for everything.** WAL mode, `busy_timeout=5000`, monotonic message IDs as cursors. Proven, boring, reliable.
- **Stateless transport.** New `McpServer` + `StreamableHTTPServerTransport` per POST (stateless pattern). All handlers close over one `bus` singleton. `res.on('close')` tears down the per-request transport — never the singleton.
- **Long-poll as the real-time primitive.** `wait_for_message` awaits an EventEmitter wakeup or a ≤25s timeout. An AbortSignal from `res.on('close')` cancels the waiter so listeners don't leak.
- **`/sync` as the hook primitive.** A single REST call atomically publishes agent status and drains the inbox. Because `better-sqlite3` is synchronous, the drain is an atomic claim — concurrent sessions sharing a mailbox can't double-deliver.

## `[ license ]`

AGPL-3.0 — see [LICENSE](./LICENSE)

---

#### `[ acknowledgments ]`

Architecture patterns adapted from [`gsd-browser-mcp`](https://github.com/jemplayer82/gsd-browser-mcp). Built with [`@modelcontextprotocol/sdk`](https://github.com/modelcontextprotocol/typescript-sdk) and [`better-sqlite3`](https://github.com/WiseLibs/better-sqlite3).

<div align="center">

`FATHOM` · sound the depths before you set a course

</div>