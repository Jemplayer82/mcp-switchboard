# Phase 11 Plan: Persistent Deploy + Inbox-Collision Resolution

**Requirements:** RESP-01 (persistent full-context responder), DEPLOY-05 (systemd unit, no inbox collision)

## Cutover steps (OpenClaw, systemd --user)
1. Stop + disable the cold daemon so Billy's inbox has no competing consumer:
   `systemctl --user stop claude-code-agent && systemctl --user disable claude-code-agent`
2. Install the unit: copy `claude-channel-agent.service` → `~/.config/systemd/user/`;
   `systemctl --user daemon-reload`; `systemctl --user enable --now claude-channel-agent`.
   (Unit env: `SWITCHBOARD_CHANNEL_AGENT_ID=Billy`, allowlist set; WorkingDirectory =
   `~/switchboard-channel` from Phase 10.)
3. Confirm: `systemctl --user status claude-channel-agent` active; `journalctl` shows the
   session + bridge started; `Billy` online on the bus.

## Verify (success criteria)
1. Unit active after enable+start; journald clean. (crit 1)
2. `systemctl --user restart claude-channel-agent` → session reconnects, re-registers,
   resumes long-poll, no manual step. (crit 2)
3. Sole consumer of Billy's inbox — cold daemon disabled; no second `wait_for_message`. (crit 3)
4. From `Claude`, `send_message` → `Billy` → context-aware reply received. (crit 4)

## Rollback
`systemctl --user disable --now claude-channel-agent` + `systemctl --user enable --now claude-code-agent`.
