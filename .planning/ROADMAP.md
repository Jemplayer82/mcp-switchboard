# Roadmap: mcp-switchboard

## Overview

Build a real-time inter-agent message bus as one centralized streamable-HTTP MCP server, then ship it into the existing `mcp-shared` Portainer stack and wire it to Claude Code and Hermes. The journey: stand up the bus core (HTTP+Bearer shell, SQLite+EventEmitter long-poll singleton, the messaging/channels/coordination tool surface), layer on presence/push-wake and the ambient awareness feed, containerize and deploy it behind a prebuilt GHCR image, wire both clients plus the Claude Code awareness hooks, then prove the whole thing end-to-end with a two-client durability test and a live Claude↔Hermes instruction→result round-trip. Single milestone, coarse granularity, five phases. The approved design (`ok-so-write-an-federated-map.md`) is the source of truth for build order.

---

## Milestone v1.0 — Bus Core + Deploy + Wire

### Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Bus Core** - Scaffold the server + singleton bus and ship messaging, channels, and coordination tools with durable long-poll delivery
- [ ] **Phase 2: Presence, Wake & Awareness** - Heartbeat presence, fire-and-forget push-wake, and the self-reported cross-agent activity feed
- [ ] **Phase 3: Ship to mcp-shared** - Prebuilt GHCR image via CI, deployed into the Portainer stack on port 3107 with a durable volume and passing healthcheck
- [ ] **Phase 4: Wire Clients & Awareness Hooks** - Connect Claude Code and Hermes over HTTP and auto-publish/auto-digest activity via Claude Code hooks
- [ ] **Phase 5: End-to-End Verify** - Prove sub-second delivery, restart durability, and a live Claude↔Hermes instruction→result round-trip

### Phase Details

#### Phase 1: Bus Core
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

#### Phase 2: Presence, Wake & Awareness
**Goal**: Agents report presence and self-published activity, idle daemons get push-woken on new mail, and any agent can pull a cross-agent activity digest.
**Depends on**: Phase 1
**Requirements**: PRES-01, PRES-02, PRES-03, AWARE-01, AWARE-02
**Success Criteria** (what must be TRUE):
  1. `list_agents` reports each agent's `online` flag derived from heartbeat/`last_seen`
  2. An agent that registered a `wake_url` gets a fire-and-forget `POST` from the bus when a message arrives with no active waiter, and the message still delivers on the next poll even if the wake fails
  3. An agent self-reports its current activity via `set_status` (activity + optional detail)
  4. `get_activity` returns a cross-agent activity feed plus a snapshot of every agent's current status and online flag
**Plans**: TBD

#### Phase 3: Ship to mcp-shared
**Goal**: The bus runs in production as a prebuilt image inside the `mcp-shared` Portainer stack on port 3107 with durable storage and a passing healthcheck.
**Depends on**: Phase 2
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03
**Success Criteria** (what must be TRUE):
  1. A GitHub Actions workflow builds and publishes `ghcr.io/jemplayer82/mcp-agentbus:latest` and the GHCR package exists
  2. The `agentbus-mcp` service runs in the `mcp-shared` stack on port 3107 with a persistent named volume, and `curl http://192.168.7.50:3107/healthz` returns `{"ok":true}`
  3. The Portainer REST deploy resupplies the full Env array so pre-existing stack secrets are not wiped, and the container shows healthy in Portainer
**Plans**: TBD

#### Phase 4: Wire Clients & Awareness Hooks
**Goal**: Claude Code and Hermes both connect to the live bus over HTTP with no per-agent bridge, and Claude Code auto-publishes its activity and auto-injects an awareness digest at turn boundaries.
**Depends on**: Phase 3
**Requirements**: CONN-03, AWARE-03
**Success Criteria** (what must be TRUE):
  1. Claude Code reaches the bus via a single `type:http` `.claude.json` entry (URL + bearer token) and can register/send/receive — no per-agent bridge or server code
  2. Hermes connects to the same HTTP MCP URL + token from its OpenClaw config and can register/send/receive
  3. Claude Code `PostToolUse`/`Stop` hooks auto-call `set_status` so activity is published without the user relaying it
  4. Claude Code `SessionStart`/`UserPromptSubmit` hooks call `get_activity` and inject a digest of others' activity into context at each turn boundary
**Plans**: TBD

#### Phase 5: End-to-End Verify
**Goal**: Empirical proof that the bus delivers sub-second, survives restarts, and carries a real Claude↔Hermes coordination exchange end to end.
**Depends on**: Phase 4
**Requirements**: VERIFY-01, VERIFY-02
**Success Criteria** (what must be TRUE):
  1. A standalone two-client test (`test/receiver.js` + `test/sender.js` over the LAN) delivers a message in <1s, delivers a pre-sent backlog on connect, and survives a mid-test container restart
  2. Claude sends a `type:'instruction'` message on a thread and Hermes replies `type:'result'` with `reply_to`, completing a full round-trip end to end
  3. `list_agents` shows both Claude and Hermes `online` during the exchange and an idle >25s poll returns a clean `timed_out:true` with no hung sockets
**Plans**: TBD

---

## Milestone v1.1 — Supergateway Fronting + Playwright Scraper

### Overview

Mount backends onto the existing `:8000` gateway endpoint, redeploy the switchboard from `main` to clear build drift, add a Playwright scraper behind the same gateway, then rewire all clients to the new single host:port and prove both backends are reachable end to end.

**Open decision (for Phase 6 planning):** Supergateway (`supercorp/supergateway`) wraps one stdio MCP process per instance. Exposing multiple backends under a single `host:port` via path routing likely requires either one supergateway instance per backend behind the existing `mcp-nginx-proxy` reverse proxy, or an equivalent path-router. The exact multiplexing mechanism is to be decided during Phase 6 planning — the roadmap does not prescribe it.

### Phases

- [ ] **Phase 6: Gateway Stand-Up + Switchboard Redeploy** - Mount the switchboard behind the `:8000` gateway with bearer auth and reconcile all stale agentbus/3108 references
- [ ] **Phase 7: Playwright Scraper Behind Gateway** - Publish a prebuilt Playwright MCP image and mount it as a second backend on the gateway
- [ ] **Phase 8: Client Rewire + End-to-End Verify** - Rewire Claude Code and other clients to gateway endpoints and prove both backends reachable through one host:port

### Phase Details

### Phase 6: Gateway Stand-Up + Switchboard Redeploy
**Goal**: The `:8000` gateway has the switchboard mounted and reachable at a stable path with bearer auth; the switchboard is running from current `main` (restoring the missing `/status`, `/activity`, `/healthz` routes); and all stale references to the retired `agentbus` stack (id 63) and host port `:3108` are reconciled across compose files and planning docs.
**Depends on**: Phase 5
**Requirements**: GATE-01, GATE-02, GATE-03, DEPLOY-04
**Success Criteria** (what must be TRUE):
  1. `curl -H "Authorization: Bearer <token>" http://192.168.7.50:8000/switchboard/mcp` returns a valid MCP response (not a bare `text/plain` 404)
  2. `curl http://192.168.7.50:<switchboard-port>/healthz` returns `{"ok":true}` confirming the redeployed `main` build is live with all routes restored
  3. The gateway stack is deployed as a prebuilt/config-only Portainer stack (no `build:` directive) and a health/up signal is observable (container shows healthy or a designated health endpoint responds)
  4. No running container, compose file, or planning doc references `agentbus` stack id 63 or the stale host port `:3108` — all references point to the current `mcp-switchboard` deployment
**Plans**: TBD
**Note**: How path-routing is achieved on `:8000` (one supergateway per backend behind nginx vs. a path-router) is an open decision — resolve during Phase 6 plan step before implementation.

### Phase 7: Playwright Scraper Behind Gateway
**Goal**: A Playwright-backed MCP server (Microsoft `@playwright/mcp`) is running behind the `:8000` gateway at its own stable path, deployed as a prebuilt image with browsers baked in, and an agent can use it to navigate a URL and extract page content.
**Depends on**: Phase 6
**Requirements**: SCRAPE-01, SCRAPE-02, SCRAPE-03
**Success Criteria** (what must be TRUE):
  1. `curl -H "Authorization: Bearer <token>" http://192.168.7.50:8000/scraper/mcp` returns a valid MCP response, confirming the scraper is mounted and routed through the gateway
  2. An agent calls a scraper MCP tool (e.g. `browser_navigate` + `browser_get_content`) through the gateway endpoint and receives extracted page text — no direct access to the scraper container port required
  3. The scraper Portainer stack uses a prebuilt `ghcr.io/jemplayer82/*` image with Playwright browsers baked in — no `build:` directive; a fresh `docker pull` + `docker run` produces a working scraper with no browser download step
**Plans**: TBD

### Phase 8: Client Rewire + End-to-End Verify
**Goal**: Claude Code (and any other active clients) are pointed at the gateway endpoints rather than direct container ports, and a single session proves that one host:port (`:8000`) reaches both the switchboard and the scraper.
**Depends on**: Phase 7
**Requirements**: CONN-04, VERIFY-03
**Success Criteria** (what must be TRUE):
  1. Claude Code's `.claude.json` MCP entries for the switchboard and scraper both point to `http://192.168.7.50:8000/<path>/mcp` — no direct `:3107`/`:3108` URLs remain for gateway-fronted servers
  2. Adding a new agent or a new backend MCP requires only a one-line path mount in the gateway config and a one-line URL entry in the client config — no new ports, no new firewall rules, no new Portainer stacks
  3. In one session, an agent successfully calls a switchboard tool AND a scraper tool both through `http://192.168.7.50:8000` — confirming the multiplex works end to end
**Plans**: TBD
**UI hint**: no

---

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Bus Core | 0/TBD | Not started | - |
| 2. Presence, Wake & Awareness | 0/TBD | Not started | - |
| 3. Ship to mcp-shared | 0/TBD | Not started | - |
| 4. Wire Clients & Awareness Hooks | 0/TBD | Not started | - |
| 5. End-to-End Verify | 0/TBD | Not started | - |
| 6. Gateway Stand-Up + Switchboard Redeploy | 0/TBD | Not started | - |
| 7. Playwright Scraper Behind Gateway | 0/TBD | Not started | - |
| 8. Client Rewire + End-to-End Verify | 0/TBD | Not started | - |
