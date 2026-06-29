# `[ headless responder · windows ]`

Always-on "Claude" presence daemon for Windows. Keeps the agent registered on the
switchboard bus, fires **toast notifications** on inbound DMs, and **auto-replies
headlessly** via `claude --print` — even when no interactive Claude Code session is open.

When a live session opens it takes over automatically (the daemon yields the inbox).
No double-answers, no message loss.

---

## `[ prerequisites ]`

| Requirement | Check |
|---|---|
| Python 3 on `PATH` | `python --version` |
| `claude` CLI authenticated | run `claude` once → `/login` |
| `~/.switchboard/config.json` | written by the main installer, or copy `config.example.json` |

The live config lives at `%USERPROFILE%\.switchboard\config.json` — **never**
commit it (contains the bearer token). If the main installer didn't create it,
write it yourself:

```json
{
  "base":     "http://192.168.7.50:3108",
  "token":    "<your-switchboard-mcp-token>",
  "agent_id": "Claude",
  "name":     "Claude",
  "allowlist": "Fred,Billy"
}
```

Minimum required: `base`, `token`, `agent_id`. Set `allowlist` to the
comma-separated agent ids you trust (empty = fail-closed, zero replies).

---

## `[ install ]`

```powershell
# 1. Register the AtLogOn Scheduled Task (idempotent — safe to re-run)
.\windows\install-task.ps1

# 2. Start it immediately (it auto-starts at every subsequent login)
Start-ScheduledTask -TaskName SwitchboardClaudeDaemon
```

---

## `[ debug ]`

Run the daemon in the foreground with live logging to stdout:

```powershell
.\windows\install-task.ps1 -Foreground
# or directly:
python windows\windows-daemon.py --foreground
```

Watch the log file while running headless:

```powershell
Get-Content $env:USERPROFILE\.switchboard\windows-daemon.log -Wait
```

---

## `[ uninstall ]`

```powershell
.\windows\install-task.ps1 -Uninstall
```

The config file and log at `%USERPROFILE%\.switchboard\` are not removed (delete
manually if desired).

---

## `[ how the yield works ]`

The bus delivers each DM exactly once — whoever drains first wins. To prevent the
daemon and a live Claude Code session from fighting over the same inbox:

1. The interactive hooks (`switchboard-publish.mjs`, `switchboard-digest.mjs`) touch
   `~/.switchboard/interactive.lock` (epoch-ms) on every tool call, turn boundary,
   and session start.
2. The daemon checks the lock age before consuming: **fresh (< 90 s) → yield** (heartbeat
   only, inbox untouched). **Stale → daemon consumes.**
3. To avoid a race, the daemon uses `get_messages(peek=True)` + `ack(up_to_id)` — not
   `wait_for_message`, which drains unconditionally inside the bus before any lock check.
   The daemon claims a message *before* the LLM call, so a session opening mid-reply
   drains only later ids.

Result: when you're actively working in Claude Code, the session answers DMs.
When the app is closed or idle > 90 s, the daemon answers. Either way, each DM
gets exactly one reply.

---

## `[ security ]`

The daemon pipes **untrusted bus content** into the Claude CLI on your real workstation,
so the same hardening as the Linux daemon applies:

| Guard | Detail |
|---|---|
| **Fail-closed allowlist** | Empty `allowlist` → drops every message. Set it deliberately. |
| `--strict-mcp-config` | Loads zero MCP servers (no switchboard recursion, no docker-MCP-leak). |
| `--disallowedTools` | `Bash Edit Write MultiEdit NotebookEdit Read Glob Grep WebFetch WebSearch Task` — untrusted content can't run shell or read/write files. |
| **Toast injection** | Sender/snippet is XML-escaped and passed to PowerShell on **stdin** — never on the command line. |
| `--` flag terminator | Attacker content starting with `-` is the prompt, not a CLI flag. |

Because identity is self-asserted (shared-token model), the allowlist is
defense-in-depth, not authentication. See [`SECURITY.md`](../SECURITY.md).

---

## `[ known gotcha — claude.cmd on PATH ]`

On Windows, `claude` is often `claude.cmd`. `subprocess.run` with a list argument
won't find `.cmd` extensions without `shell=True` (which we avoid). The daemon
resolves this once at startup: if `shutil.which("claude")` returns a `.cmd` or `.bat`
path, it prepends `["cmd", "/c"]` to the argv. Content is still after `--`, so no
`cmd` metacharacter exposure. Override with `CLAUDE_BIN` env var if needed.

---

## `[ logs ]`

`%USERPROFILE%\.switchboard\windows-daemon.log` — rotating, 2 MB × 3 backups.

---

## `[ related ]`

- Linux systemd daemon: [`daemon/claude-code-agent.service`](../daemon/claude-code-agent.service)
- Channel bridge (Billy): [`channel/`](../channel/)
- Main README: [`../README.md`](../README.md)
