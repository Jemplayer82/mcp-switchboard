# Phase 11 Summary: Persistent Deploy + Inbox-Collision Resolution

**Result:** ✅ The headless full-context channel responder runs as a systemd user unit on
OpenClaw under the **Billy** id; the cold `claude-code-agent` daemon is retired. Billy's inbox
has exactly one consumer.

## What changed on OpenClaw
- `claude-code-agent.service` (cold `claude --print` daemon) — **stopped + disabled** (reversible).
- `claude-channel-agent.service` installed to `~/.config/systemd/user/`, **enabled + running**
  (`Main PID … python3` → `run-channel-session.py` → interactive `claude --channels` in a sized pty).
- Responder id `Billy`; allowlist `Claude,Fred,Hermes,node24-upgrade,claude-code`.
- Reuses the Phase 10 deploy dir `~/switchboard-channel/`.

## Live verification
| Criterion | Result |
|-----------|--------|
| Unit active after enable+start; channel loaded | ✅ `active (running)`; "Channels … inject directly in this session" |
| Cold daemon retired → sole inbox consumer | ✅ `claude-code-agent` inactive + disabled |
| DM `Claude`→`Billy` gets a context-aware reply | ✅ msg 4377 → 4381 `CUTOVER-OK-71M` + `host: OpenClaw, cwd: /home/landon/switchboard-channel` |
| `systemctl --user restart` → auto-recovers, re-registers, replies | ✅ unit `active`, channel reloaded, msg 4386 → 4389 `REREG-OK-30J` — no manual step |

## Net effect
Bus agents that message **Billy** now reach a persistent, full-context Claude session in real
time (vs. the old amnesiac per-message `claude --print`). This is the milestone's core value,
delivered. RESP-01 + DEPLOY-05 satisfied.

## Carry to Phase 12 / 13
- Context grows unbounded across messages → Phase 12 hourly compaction/rotation (the unit
  restart path is proven clean, so rotation via a systemd timer is low-risk).
- Billy is live with `--dangerously-skip-permissions` + bus-content injection → Phase 13 audit.
- Per-turn Opus cost is now a live, ongoing cost.
