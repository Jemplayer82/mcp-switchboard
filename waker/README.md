# `[ session waker ]`

Part of the [mcp-switchboard](../README.md) docs.

The hooks deliver mail only when a Claude Code session takes a turn, and an idle session never takes one on its own. The waker closes that gap. Every 2 minutes it checks the bus and, when a mapped agent id has new unread direct messages, sends one short nudge into the matching local Claude Code session (a Desktop session or a `claude --bg` session). The nudge starts a turn, and the hooks then deliver the mail:

> Switchboard: new message #1234 for claude-code on thread deploy from fred; read it with get_messages (agent_id claude-code) and reply there.

Only the message id, thread and sender go into the nudge, never the message content.

## `[ how it delivers ]`

The nudge is a cross-session message, the same mechanism as Claude Code's SendMessage tool. It's sent by a short headless run:

```bash
claude -p --model haiku --tools SendMessage,ListAgents --strict-mcp-config \
  --settings '{"disableAllHooks":true}' --no-session-persistence ...
```

- The run can only list sessions and send that one message. It has no MCP servers and no shell or file tools.
- Hooks are off. Otherwise the switchboard hooks in the sending run would drain the shared inbox.
- The waker reads the result of the SendMessage call itself, not the model's summary of it.
- Cost: about $0.001 per nudge on Haiku. Nothing runs when there's no new mail.

> [!IMPORTANT]
> **Permission modes.** Claude Code holds a cross-session message for approval when the sender's permission-mode class (bypass vs. prompting) differs from the target's. The waker sends in the mode the target session was launched with: `bypassPermissions` if the target was launched that way, otherwise `auto`. If you change a session's mode later, set `"sender_mode"` on its mapping, or nudges will wait in that session as held messages.

## `[ dedupe and rate limits ]`

- **Each message counts once.** The waker reads bus history with `since_id`, which never moves anyone's read cursor. Before nudging, it drops messages the agent has already read (found with `peek: true`). It never marks anything read.
- **Rate limits per session:** at most one nudge every `min_interval_min` (default 10) and at most `max_nudges_per_hour` per hour (default 4). Messages that arrive in between are combined into the next nudge, for example "3 unread messages #a-#b from ... on threads ...".
- **No backlog flood on first run:** scanning starts at the current end of the bus, so an existing backlog never floods a session.
- If a mapped session isn't running, the waker logs it and retries on later runs. It doesn't start sessions.

## `[ install ]` (Linux, systemd user units)

```bash
install -Dm755 waker/switchboard_waker.py ~/.local/bin/switchboard_waker.py
install -Dm644 waker/sessions.example.json ~/.config/switchboard-waker/sessions.json
cp waker/switchboard-waker.{service,timer} ~/.config/systemd/user/
$EDITOR ~/.config/switchboard-waker/sessions.json
python3 ~/.local/bin/switchboard_waker.py --dry-run
systemctl --user daemon-reload && systemctl --user enable --now switchboard-waker.timer
```

The bus URL (`base` + `/mcp`) and token come from `~/.switchboard/config.json`, the same file the hooks use. If the token lives in an environment variable instead, put `SWITCHBOARD_MCP_TOKEN=...` in `~/.config/switchboard-waker/env`. The variable name follows `token_env` in the hook config.

Other `settings` keys in `sessions.json`:

| key | default | notes |
| --- | --- | --- |
| `switchboard_url` | `<base>/mcp` | override the MCP endpoint |
| `claude_bin` | `claude` on `PATH` | systemd user units often have a short `PATH`, so set an absolute path |
| `sender_cwd` | `~` | must be a folder Claude Code already trusts, or `claude -p` refuses to start |
| `sender_model` | `haiku` | |
| `min_interval_min` / `max_nudges_per_hour` | `10` / `4` | can also be set on a single mapping |

## `[ add or remove a session ]`

Each mapping links a switchboard agent id to a session name. Use the name exactly as the app sidebar shows it (`claude agents --json` lists them):

```json
{"agent_id": "claude-code", "session": "My main session"}
```

- **Add:** append a line like the one above. It takes effect on the next run, with no reload needed.
- **Remove:** delete the line, or set `"enabled": false` to pause it.

Logs: `journalctl --user -u switchboard-waker -f`. State: `~/.local/state/switchboard-waker/state.json`.
