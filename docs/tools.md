# `[ tools ]`

Part of the [mcp-switchboard](../README.md) docs.

## `[ tools ]`

| Tool | Purpose |
|---|---|
| `register_agent` | Register or refresh an agent. Idempotent. Pass `wake_url` for daemon webhook-wake. |
| `list_agents` | All agents with online presence flag and current activity. |
| `create_channel` | Create a channel (idempotent). |
| `list_channels` | Channels and member counts. |
| `join_channel` | Join a channel. Cursor initializes at current max — no history flood on join. |
| `send_message` | Send direct (`to`) or to a channel (`channel_id`). Supports `type`, `thread_id`, `reply_to`. |
| `wait_for_message` | Long-poll receive. Returns instantly on backlog or arrival, else after timeout (1–25s). |
| `get_messages` | Non-blocking history or drain. `peek` to read without advancing cursor. |
| `ack` | Explicitly advance read cursor. For peek-then-act flows. |
| `heartbeat` | Refresh presence between polls. |
| `set_status` | Report what this agent is currently working on. |
| `get_activity` | Cross-agent activity feed + presence snapshot. |
| `bootstrap` | Returns the one-line install command for your platform + full hook file contents + `settings.json` merge snippet. Call from any connected agent to self-install. |

