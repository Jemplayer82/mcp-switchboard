# Requirements: mcp-switchboard

**Defined:** 2026-06-09 (v1) · 2026-06-11 (v1.1) · 2026-06-16 (v1.2)
**Core Value:** Two agents exchange a message in real time with zero per-agent custom plumbing.

## v1 Requirements

### Connectivity

- [ ] **CONN-01**: Any MCP-capable agent connects to the bus via one streamable-HTTP URL (`http://192.168.7.50:3107/mcp`) authenticated by a shared bearer token
- [ ] **CONN-02**: An agent registers itself idempotently on startup via `register_agent` (id, name, optional capabilities)
- [ ] **CONN-03**: Adding a new agent requires only one HTTP MCP config entry — no per-agent bridge or server code

### Messaging

- [ ] **MSG-01**: An agent can send a direct message to another agent by id
- [ ] **MSG-02**: An agent can broadcast to a named channel it has joined
- [ ] **MSG-03**: An actively-waiting agent receives a new message in <1s via long-poll (`wait_for_message`)
- [ ] **MSG-04**: Messages persist in SQLite and survive a container restart (backlog delivered on reconnect)
- [ ] **MSG-05**: Each agent has a read cursor so a message drains once and is not redelivered
- [ ] **MSG-06**: `get_messages` returns history/unread without blocking, with a peek option that does not advance the cursor

### Channels

- [ ] **CHAN-01**: An agent can create a channel idempotently
- [ ] **CHAN-02**: An agent can list channels with member counts
- [ ] **CHAN-03**: An agent can join a channel; joining starts its cursor at the current head (no history flood)

### Coordination

- [ ] **COORD-01**: Messages carry `type` (chat/instruction/result/status), `thread_id`, and `reply_to` for structured exchanges
- [ ] **COORD-02**: A worker can peek an instruction and `ack` it after acting, so a crash mid-task does not lose the instruction

### Presence & Wake

- [ ] **PRES-01**: `list_agents` reports each agent's online status from heartbeat/last_seen
- [ ] **PRES-02**: A daemon agent can register a `wake_url`; the bus POSTs to it when a message arrives with no active waiter (push-wake)
- [ ] **PRES-03**: Push-wake is fire-and-forget — a failed wake still delivers the (durable) message on the next poll

### Awareness

- [ ] **AWARE-01**: An agent self-reports current activity via `set_status` (activity + optional detail)
- [ ] **AWARE-02**: `get_activity` returns a cross-agent activity feed plus a snapshot of each agent's current status and online flag
- [ ] **AWARE-03**: Claude Code hooks auto-publish activity (PostToolUse/Stop) and auto-inject a digest of others' activity at each turn boundary (SessionStart/UserPromptSubmit) without the user relaying

### Deployment

- [ ] **DEPLOY-01**: The server builds to a prebuilt image `ghcr.io/jemplayer82/mcp-agentbus:latest` via GitHub Actions
- [ ] **DEPLOY-02**: The service runs in the `mcp-shared` Portainer stack on port 3107 with a persistent named volume and passes `/healthz`
- [ ] **DEPLOY-03**: Deploy via Portainer REST resupplies the full Env array so existing stack secrets are not wiped

### Verification

- [ ] **VERIFY-01**: A standalone two-client test proves sub-second delivery, backlog durability, and restart persistence
- [ ] **VERIFY-02**: Claude ↔ Hermes complete an instruction→result round-trip end to end

## v1.1 Requirements — Supergateway Fronting + Playwright Scraper

### Gateway

- [ ] **GATE-01**: Every backend MCP server is reachable through one supergateway endpoint on `192.168.7.50:8000` via path routing — clients use a single host:port for all servers
- [ ] **GATE-02**: The switchboard MCP is reachable through the gateway at a stable path (e.g. `:8000/switchboard/mcp`) with the shared bearer token authenticating end to end
- [ ] **GATE-03**: The gateway runs as a prebuilt/config-only Portainer stack (no `build:` context) with durable config and an observable health/up signal

### Scraper

- [ ] **SCRAPE-01**: A Playwright-backed MCP server (Microsoft `@playwright/mcp`) is exposed as streamable-HTTP behind the gateway at its own path (e.g. `:8000/scraper/mcp`)
- [ ] **SCRAPE-02**: An agent can drive the scraper through the gateway to navigate to a URL and extract page content/text via its MCP tools
- [ ] **SCRAPE-03**: The scraper deploys as a prebuilt image with Playwright browsers baked in — no build context on Portainer/edge

### Connectivity (v1.1)

- [ ] **CONN-04**: Claude Code (and other clients) are rewired to the gateway endpoint(s); adding a new agent or a new backend MCP stays a one-line config/mount change

### Deployment (v1.1)

- [ ] **DEPLOY-04**: The live switchboard is redeployed from current `main` (restoring `/status`, `/activity`, `/healthz`) and the retired `agentbus` stack (id 63) / `:3108` references are reconciled across compose + planning docs

### Verification (v1.1)

- [ ] **VERIFY-03**: In one session an agent reaches BOTH the switchboard and the scraper through the single `:8000` gateway (one host:port, two backends), proving the multiplex works end to end

## v1.2 Requirements — Headless Full-Context Channel Responder

### Responder & Channel Bridge

- [ ] **RESP-01**: A persistent headless `claude --channels` session on OpenClaw answers bus messages with full conversation context (not a fresh per-message process), staying alive while idle between messages
- [ ] **RESP-02**: A Node `switchboard-channel` MCP bridge long-polls the bus for the responder's agent id and injects each inbound message into the session as a `claude/channel` event in <1s
- [ ] **RESP-03**: The bridge exposes a reply tool the session calls to send its answer back to the original sender on the bus, preserving `reply_to`/`thread_id`
- [ ] **RESP-04**: The bridge enforces a sender allowlist — only approved agent ids are injected as events; messages from anyone else are dropped before reaching the session

### Verification (v1.2)

- [ ] **VERIFY-04**: A spike proves a headless `claude --channels` session (no TTY, OpenClaw `claude` 2.1.179) stays alive while idle and autonomously fires a turn on a pushed channel event — this gates the rest of the milestone
- [ ] **VERIFY-05**: End to end, a bus agent (e.g. Fred) sends a DM while no interactive session is open and receives a context-aware reply within ~2s, with the responder process still alive afterward

### Deployment (v1.2)

- [ ] **DEPLOY-05**: The responder runs as a systemd user unit on OpenClaw (auto-restart, journald logs) without colliding with the existing `claude-code-agent` cold daemon's inbox — resolved via a dedicated agent id or by retiring the cold daemon

### Context Management

- [ ] **CTX-01**: The responder's context is bounded on an hourly cadence — true `/compact` if it can be driven into the session, otherwise automatic hourly session rotation — without the responder dropping off the bus

### Security (v1.2)

- [ ] **SEC-02**: A security audit covers the channel-injection path into the `--dangerously-skip-permissions` session (prompt injection, allowlist bypass, tool-abuse blast radius); findings are triaged and either mitigated or explicitly accepted

## v2 Requirements

### Security

- **SEC-01**: Per-agent bearer tokens (token→agent_id map) replacing the single shared token

### Awareness

- **AWARE-04**: Web dashboard rendering live presence + activity feed

## Out of Scope

| Feature | Reason |
|---------|--------|
| Separate broker (Redis/NATS/RabbitMQ) | One centralized MCP server holds shared state; a broker adds a container and failure mode for no benefit at this scale |
| Multi-replica / horizontal scale | Single-writer SQLite + in-process EventEmitter assume exactly one container |
| Waking an idle interactive Claude session mid-idle | Impossible over MCP — an LLM not executing can't perceive anything; mitigated by turn-boundary digest hooks, not solved |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONN-01 | Phase 1 | Pending |
| CONN-02 | Phase 1 | Pending |
| MSG-01 | Phase 1 | Pending |
| MSG-02 | Phase 1 | Pending |
| MSG-03 | Phase 1 | Pending |
| MSG-04 | Phase 1 | Pending |
| MSG-05 | Phase 1 | Pending |
| MSG-06 | Phase 1 | Pending |
| CHAN-01 | Phase 1 | Pending |
| CHAN-02 | Phase 1 | Pending |
| CHAN-03 | Phase 1 | Pending |
| COORD-01 | Phase 1 | Pending |
| COORD-02 | Phase 1 | Pending |
| PRES-01 | Phase 2 | Pending |
| PRES-02 | Phase 2 | Pending |
| PRES-03 | Phase 2 | Pending |
| AWARE-01 | Phase 2 | Pending |
| AWARE-02 | Phase 2 | Pending |
| DEPLOY-01 | Phase 3 | Pending |
| DEPLOY-02 | Phase 3 | Pending |
| DEPLOY-03 | Phase 3 | Pending |
| CONN-03 | Phase 4 | Pending |
| AWARE-03 | Phase 4 | Pending |
| VERIFY-01 | Phase 5 | Pending |
| VERIFY-02 | Phase 5 | Pending |
| GATE-01 | Phase 6 | Pending |
| GATE-02 | Phase 6 | Pending |
| GATE-03 | Phase 6 | Pending |
| DEPLOY-04 | Phase 6 | Pending |
| SCRAPE-01 | Phase 7 | Pending |
| SCRAPE-02 | Phase 7 | Pending |
| SCRAPE-03 | Phase 7 | Pending |
| CONN-04 | Phase 8 | Pending |
| VERIFY-03 | Phase 8 | Pending |
| VERIFY-04 | Phase 9 | Pending |
| RESP-02 | Phase 10 | Pending |
| RESP-03 | Phase 10 | Pending |
| RESP-04 | Phase 10 | Pending |
| RESP-01 | Phase 11 | Pending |
| DEPLOY-05 | Phase 11 | Pending |
| CTX-01 | Phase 12 | Pending |
| SEC-02 | Phase 13 | Pending |
| VERIFY-05 | Phase 13 | Pending |

**Coverage:**
- v1.0 requirements: 22 total — mapped 22/22 (100%, phases 1–5)
- v1.1 requirements: 9 total — mapped 9/9 (100%, phases 6–8)
- v1.2 requirements: 9 total — mapped 9/9 (100%, phases 9–13)
- Cumulative: 40 requirements, 40 mapped, 0 unmapped

---
*Last updated: 2026-06-17 after v1.2 roadmap creation*
