# Retrospective — mcp-switchboard

## Milestone: v1.2 — Headless Full-Context Channel Responder

**Shipped:** 2026-06-17
**Phases:** 5 (9–13) | **Plans:** 5 | **Audit:** PASSED (9/9 requirements)

### What Was Built
A persistent, full-context `claude --channels` session (`Billy`) on OpenClaw, fronted by a Node
`switchboard-channel` MCP bridge, replacing the cold spawn-and-die `claude --print` daemon. Bus
agents now get real-time, context-keeping replies even with no interactive session open.

### What Worked
- **Spike-first gating.** Phase 9 ran the risky unknown (headless channels) as a live go/no-go
  before any bridge code. It surfaced five dead-end launch forms; finding the one that works
  (interactive + sized pty + auto-confirm + trust) early saved the whole build from false starts.
- **Test under a throwaway id, cut over last.** Phase 10 verified the bridge as `Claude-rc-test`
  so the live cold daemon was untouched until the Phase 11 cutover — zero-risk iteration.
- **Verify on real hardware with unique tokens.** Every claim was proven by a live bus round-trip
  (PONG/LONGEVITY/CUTOVER/REREG tokens, real-Fred E2E), not by inspection.

### What Was Inefficient
- Discovering the headless launch recipe took several SSH iterations (EOF-exit, `-p` exits,
  stream-json no-fire, blank `script` pty) before the Python sized-pty + auto-confirm worked.
  A capability matrix for `claude` run-modes would have shortcut this.
- `--dangerously-load-development-channels` shows a per-launch confirm dialog; auto-confirming via
  pty keystroke works but is brittle. Allowlisting the bridge as a plugin would be cleaner.

### Patterns Established
- **pty harness** (`run-channel-session.py`): sized `openpty` + held-open stdin + auto-confirm +
  exit-with-child for systemd restart — the reusable way to run an interactive Claude headless.
- **Bridge = MCP channel + bus long-poll + reply tool + sender allowlist**, fail-closed.
- **Security-by-default**: `--disallowedTools` to bound blast radius on a bypass-permissions,
  untrusted-input session.

### Key Lessons
- Channels only fire turns in **interactive** mode, never `-p`/stream-json — the single most
  important finding; everything else followed from it.
- `agent_id` is client-asserted on the shared-token bus → the sender allowlist is not an identity
  boundary against a token holder. Per-agent tokens (v2 SEC-01) is the real fix.
- Each channel turn is a full Opus turn (~$0.10+) — a persistent responder has real ongoing cost.

### Cost Observations
- Model: Opus 4.8 for the responder (1M context). Verification consumed a handful of live turns.
- Notable: backgrounding the long idle/compaction waits kept the build moving without blocking.

## Cross-Milestone Trends
- v1.0 stood up the bus; v1.2 made an always-on, context-keeping consumer of it. Recurring theme:
  MCP can't push to an idle LLM — the answer is always a harness that long-polls or is kept alive.
