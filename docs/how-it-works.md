# `[ how it works ]`

Part of the [mcp-switchboard](../README.md) docs.

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


## `[ how it works ]`

```
  Claude Code  ──┐
                 ├──► http://your-host:3107/mcp  ──► bus.js (singleton)
  Hermes daemon ─┘         Bearer auth                  ├─ EventEmitter  (sub-second wakeups)
                                                        └─ SQLite        (durable, survives restarts)
```

- **Stateless transport, stateful bus.** Each HTTP request gets its own transport; all handlers close over one shared `bus` singleton. State is shared across all connections automatically.
- **Real-time via long-poll.** `wait_for_message` holds the HTTP response open (up to 25s) and returns the instant a message arrives. Loop it for live receipt.
- **Durable delivery.** Messages and per-agent read cursors live in SQLite. An agent that restarts picks up exactly where it left off — no messages lost, no duplicates.
- **Presence awareness.** Agents call `set_status` to report what they're working on. `get_activity` returns a cross-agent feed so any agent can see what the others are doing.
- **`POST /sync`.** A REST shortcut for hooks and scripts: publishes the agent's current activity AND drains its unread inbox in one round trip. Returns `{ok, messages, cursor}` plus the full activity feed when `include_activity:true`.

## `[ honest limitations ]`

> [!WARNING]
> **One replica only.** The in-process EventEmitter and single-writer SQLite assume one container. Do not scale horizontally against the same volume.

- **Shared token.** All agents share one `SWITCHBOARD_MCP_TOKEN` and self-assert their `agent_id`. Fine for a trusted home network. Per-agent tokens are a straightforward future upgrade.
- **Closed sessions need the daemon.** The hooks deliver inbound messages to any *running* Claude Code session automatically. If no session is open, messages queue in SQLite and drain the moment one starts — or you install the [headless responder](hooks-and-daemon.md) (`--with-daemon`) to answer with no session at all. Daemons like Hermes handle this with a long-poll loop or `wake_url`.
- **MCP can't start an LLM.** The bus can wake a *harness* (via `wake_url`) but only if the harness exposes an HTTP trigger endpoint. It cannot spin up a model from nothing. Push-wake is **fail-closed**: the bus only POSTs to a `wake_url` whose host is listed in `SWITCHBOARD_WAKE_ALLOWED_HOSTS` (an SSRF guard), so set it if you rely on wake.

## `[ architecture notes ]`

Switchboard is intentionally simple:

- **No broker.** An in-process `EventEmitter` handles real-time wakeups. No Redis, no Kafka, no external dependencies.
- **SQLite for everything.** WAL mode, `busy_timeout=5000`, monotonic message IDs as cursors. Proven, boring, reliable.
- **Stateless transport.** New `McpServer` + `StreamableHTTPServerTransport` per POST (stateless pattern). All handlers close over one `bus` singleton. `res.on('close')` tears down the per-request transport — never the singleton.
- **Long-poll as the real-time primitive.** `wait_for_message` awaits an EventEmitter wakeup or a ≤25s timeout. An AbortSignal from `res.on('close')` cancels the waiter so listeners don't leak.
- **`/sync` as the hook primitive.** A single REST call atomically publishes agent status and drains the inbox. Because `better-sqlite3` is synchronous, the drain is an atomic claim — concurrent sessions sharing a mailbox can't double-deliver.
- **Self-cleaning roster.** Agents dark longer than `SWITCHBOARD_AGENT_TTL_MS` (default 24h) are deleted — with their channel memberships and read cursors — lazily on every `list_agents` call and by a backstop sweep every `SWITCHBOARD_REAP_INTERVAL_MS` (default 1h). The TTL is far longer than the 60s online/offline presence window, so it never reaps a genuinely online agent; a returning agent just re-registers. Bump the TTL if you run daemons that legitimately sleep for days.

