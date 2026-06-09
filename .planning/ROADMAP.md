# Roadmap: mcp-agentbus

## Overview

Build a real-time inter-agent message bus as one centralized streamable-HTTP MCP server, then ship it into the existing `mcp-shared` Portainer stack and wire it to Claude Code and Hermes. The journey: stand up the bus core (HTTP+Bearer shell, SQLite+EventEmitter long-poll singleton, the messaging/channels/coordination tool surface), layer on presence/push-wake and the ambient awareness feed, containerize and deploy it behind a prebuilt GHCR image, wire both clients plus the Claude Code awareness hooks, then prove the whole thing end-to-end with a two-client durability test and a live Claude↔Hermes instruction→result round-trip. Single milestone, coarse granularity, five phases. The approved design (`ok-so-write-an-federated-map.md`) is the source of truth for build order.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Bus Core** - Scaffold the server + singleton bus and ship messaging, channels, and coordination tools with durable long-poll delivery
- [ ] **Phase 2: Presence, Wake & Awareness** - Heartbeat presence, fire-and-forget push-wake, and the self-reported cross-agent activity feed
- [ ] **Phase 3: Ship to mcp-shared** - Prebuilt GHCR image via CI, deployed into the Portainer stack on port 3107 with a durable volume and passing healthcheck
- [ ] **Phase 4: Wire Clients & Awareness Hooks** - Connect Claude Code and Hermes over HTTP and auto-publish/auto-digest activity via Claude Code hooks
- [ ] **Phase 5: End-to-End Verify** - Prove sub-second delivery, restart durability, and a live Claude↔Hermes instruction→result round-trip

## Phase Details

### Phase 1: Bus Core
**Goal**: A running MCP server with the full messaging/channels/coordination tool surface, where agents register, send, and durably receive messages with sub-second long-poll delivery.
**Depends on**: Nothing (first phase)
**Requirements**: CONN-01, CONN-02, MSG-01, MSG-02, MSG-03, MSG-04, MSG-05, MSG-06, CHAN-01, CHAN-02, CHAN-03, COORD-01, COORD-02
**Success Criteria** (what must be TRUE):
  1. An agent connects over `http://<host>:3107/mcp` with a bearer token and registers itself idempotently via `register_agent`
  2. An agent sends a direct message to another agent and a channel broadcast to a channel it joined; an actively-waiting recipient receives it in <1s via `wait_for_message`
  3. Messages persist in SQLite and survive a process restart — backlog is delivered on reconnect and each agent's read cursor drains a message once (no redelivery)
  4. An agent creates/joins/lists channels idempotently, and joining starts the cursor at the current head with no history flood
  5. Messages carry `type`/`thread_id`/`reply_to`, and `get_messages` peek + `ack` let a worker read an instruction without losing it on a mid-task crash
**Plans**: TBD

### Phase 2: Presence, Wake & Awareness
**Goal**: Agents report presence and self-published activity, idle daemons get push-woken on new mail, and any agent can pull a cross-agent activity digest.
**Depends on**: Phase 1
**Requirements**: PRES-01, PRES-02, PRES-03, AWARE-01, AWARE-02
**Success Criteria** (what must be TRUE):
  1. `list_agents` reports each agent's `online` flag derived from heartbeat/`last_seen`
  2. An agent that registered a `wake_url` gets a fire-and-forget `POST` from the bus when a message arrives with no active waiter, and the message still delivers on the next poll even if the wake fails
  3. An agent self-reports its current activity via `set_status` (activity + optional detail)
  4. `get_activity` returns a cross-agent activity feed plus a snapshot of every agent's current status and online flag
**Plans**: TBD

### Phase 3: Ship to mcp-shared
**Goal**: The bus runs in production as a prebuilt image inside the `mcp-shared` Portainer stack on port 3107 with durable storage and a passing healthcheck.
**Depends on**: Phase 2
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03
**Success Criteria** (what must be TRUE):
  1. A GitHub Actions workflow builds and publishes `ghcr.io/jemplayer82/mcp-agentbus:latest` and the GHCR package exists
  2. The `agentbus-mcp` service runs in the `mcp-shared` stack on port 3107 with a persistent named volume, and `curl http://192.168.7.50:3107/healthz` returns `{"ok":true}`
  3. The Portainer REST deploy resupplies the full Env array so pre-existing stack secrets are not wiped, and the container shows healthy in Portainer
**Plans**: TBD

### Phase 4: Wire Clients & Awareness Hooks
**Goal**: Claude Code and Hermes both connect to the live bus over HTTP with no per-agent bridge, and Claude Code auto-publishes its activity and auto-injects an awareness digest at turn boundaries.
**Depends on**: Phase 3
**Requirements**: CONN-03, AWARE-03
**Success Criteria** (what must be TRUE):
  1. Claude Code reaches the bus via a single `type:http` `.claude.json` entry (URL + bearer token) and can register/send/receive — no per-agent bridge or server code
  2. Hermes connects to the same HTTP MCP URL + token from its OpenClaw config and can register/send/receive
  3. Claude Code `PostToolUse`/`Stop` hooks auto-call `set_status` so activity is published without the user relaying it
  4. Claude Code `SessionStart`/`UserPromptSubmit` hooks call `get_activity` and inject a digest of others' activity into context at each turn boundary
**Plans**: TBD

### Phase 5: End-to-End Verify
**Goal**: Empirical proof that the bus delivers sub-second, survives restarts, and carries a real Claude↔Hermes coordination exchange end to end.
**Depends on**: Phase 4
**Requirements**: VERIFY-01, VERIFY-02
**Success Criteria** (what must be TRUE):
  1. A standalone two-client test (`test/receiver.js` + `test/sender.js` over the LAN) delivers a message in <1s, delivers a pre-sent backlog on connect, and survives a mid-test container restart
  2. Claude sends a `type:'instruction'` message on a thread and Hermes replies `type:'result'` with `reply_to`, completing a full round-trip end to end
  3. `list_agents` shows both Claude and Hermes `online` during the exchange and an idle >25s poll returns a clean `timed_out:true` with no hung sockets
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Bus Core | 0/TBD | Not started | - |
| 2. Presence, Wake & Awareness | 0/TBD | Not started | - |
| 3. Ship to mcp-shared | 0/TBD | Not started | - |
| 4. Wire Clients & Awareness Hooks | 0/TBD | Not started | - |
| 5. End-to-End Verify | 0/TBD | Not started | - |
