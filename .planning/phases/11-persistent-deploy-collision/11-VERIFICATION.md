---
phase: 11
status: passed
verified: 2026-06-16
requirements: [RESP-01, DEPLOY-05]
---

# Phase 11 Verification: Persistent Deploy + Inbox-Collision Resolution

**Verdict: PASSED.** Channel responder live as a systemd user unit under `Billy`; cold daemon retired.

## Success criteria
- [x] **Unit active after enable+start; journald shows session + bridge started cleanly.**
  `systemctl --user status claude-channel-agent` → `active (running)`, Main PID python3; session.log shows the channel banner. (RESP-01)
- [x] **Restart reconnects + re-registers + resumes long-poll, no manual intervention.**
  `systemctl --user restart` → `active`, channel reloaded; DM 4386 → reply 4389 `REREG-OK-30J`. (RESP-01)
- [x] **Only one consumer drains the responder inbox (cold daemon retired).**
  `claude-code-agent` stopped + disabled (`inactive`); responder is the sole `wait_for_message` consumer of `Billy`. (DEPLOY-05)
- [x] **A bus agent DM gets a reply — alive, context-keeping, collision-free.**
  `Claude`→`Billy` msg 4377 → reply 4381 `CUTOVER-OK-71M` with correct host/cwd (context-aware). (RESP-01, DEPLOY-05)

## Human verification
None required — verified via systemctl status, journald, and live bus round-trips.

## Rollback (documented, not exercised)
`systemctl --user disable --now claude-channel-agent` + `systemctl --user enable --now claude-code-agent`.
