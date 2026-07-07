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
  "allowlist": "*"
}
```

Minimum required: `base`, `token`, `agent_id`. For `allowlist`:
- `"*"` — allow any token holder (recommended for trusted-LAN deployments where the token is the security boundary)
- `"Fred,Billy"` — comma-separated explicit list
- omit / `""` — fail-closed, drops every message

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

## `[ known gotchas ]`

**`claude.cmd` on PATH.** On Windows, `claude` is often `claude.cmd`. `subprocess.run`
with a list argument won't find `.cmd` extensions without `shell=True` (which we avoid).
The daemon resolves this once at startup: if `shutil.which("claude")` returns a `.cmd`
or `.bat` path, it prepends `["cmd", "/c"]` to the argv. Content is still after `--`, so
no `cmd` metacharacter exposure. Override with `CLAUDE_BIN` env var if needed.

**Console windows flashing on every reply.** The daemon runs as `pythonw.exe` (no
console of its own). Any subprocess it spawns — the `claude --print` reply, the toast's
`powershell` call — gets a *brand new* console window from Windows unless told
otherwise, since there's no parent console to inherit. Both spawns pass
`creationflags=subprocess.CREATE_NO_WINDOW` to suppress this. If you ever see cmd boxes
flashing open in step with bus traffic, check that flag is still present on both
`subprocess.run` calls.

**Headless `claude --print` auth can fail independently of your interactive session.**
`claude auth status` and an open interactive session can both report logged-in while a
*fresh* `claude --print` invocation still gets `401 Invalid authentication credentials`
— non-interactive invocations re-read credentials from disk and don't share whatever
session state an already-running interactive session is using. The daemon does **not**
forward that raw CLI failure to the sender as if it were a real reply (it used to — see
below) — it logs the failure and stays silent instead. If DMs stop getting auto-replies,
tail the log for `run_claude failed ... — not replying` and run `claude login` again.

**Fixed: raw CLI failures were being sent as replies.** Earlier versions of `run_claude()`
returned `stdout or stderr` without checking the exit code, so an auth failure's stderr
text got forwarded to the sender as if Claude had genuinely answered "Failed to
authenticate. API Error: 401 Invalid authentication credentials." A sender trying to be
helpful about that "error" would reply, the daemon would try to answer *that* the same
broken way, and so on — a self-sustaining loop with no code-level bug on either end,
just two agents taking a subprocess failure at face value. `run_claude()` now raises on
a nonzero exit code, and `handle_message()` logs and skips the reply instead of relaying
the failure text.

---

## `[ logs ]`

`%USERPROFILE%\.switchboard\windows-daemon.log` — rotating, 2 MB × 3 backups.

---

## `[ related ]`

- Linux systemd daemon: [`daemon/claude-code-agent.service`](../daemon/claude-code-agent.service)
- Channel bridge (Billy): [`channel/`](../channel/)
- Main README: [`../README.md`](../README.md)
