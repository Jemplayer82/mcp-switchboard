# Milestones

## v1.2 Headless Full-Context Channel Responder (Shipped: 2026-06-17)

**Phases completed:** 5 phases, 5 plans, 0 tasks

**Delivered:** Replaced the cold spawn-and-die daemon with one persistent, full-context `claude --channels` session on OpenClaw (id `Billy`), fronted by a Node `switchboard-channel` MCP bridge — bus agents now get real-time, context-keeping replies even when no interactive session is open.

**Key accomplishments:**

- Proved (live spike) a headless no-TTY `claude --channels` session stays alive idle and autonomously fires a turn on a pushed event — recipe: interactive in a sized Python pty + auto-confirm dev-channels dialog + pre-accepted trust (VERIFY-04).
- Built `switchboard-channel.mjs` — Node MCP channel bridge: long-poll → inject events → `reply` tool → bus, with a sender allowlist (RESP-02/03/04), verified live.
- Deployed as a systemd user unit under `Billy`, retiring the cold `claude-code-agent` daemon so existing senders reach the live responder transparently (RESP-01, DEPLOY-05).
- Hourly in-session `/compact` context bounding that preserves continuity (verified: memory survived compaction) (CTX-01).
- Security audit + mitigations (M1 tool-restriction, M2 rate-limit/cap, M3 hardened instructions); injection probe refused; real-Fred end-to-end round trip verified (SEC-02, VERIFY-05).

**Tag:** v1.2 · **Audit:** PASSED (9/9 reqs) · Full detail in `.planning/milestones/v1.2-*`

---
