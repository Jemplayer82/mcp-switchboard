# Requirements: mcp-agentbus

**Defined:** 2026-06-09
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
| (filled by roadmap) | — | Pending |

**Coverage:**
- v1 requirements: 22 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 22 ⚠️

---
*Last updated: 2026-06-09 after initialization*
