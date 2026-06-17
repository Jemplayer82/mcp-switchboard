# Phase 9 Plan: Headless Channel Spike

**Requirement:** VERIFY-04 (gating)
**Approach:** Run a real headless `claude --channels` session on OpenClaw against a throwaway
Node channel; push a synthetic event; observe an autonomous tool-call reply with a unique token.

## Harness (built on OpenClaw `~/chan-spike/`)
- `webhook.mjs` — minimal two-way Node channel (MCP stdio): `claude/channel` capability,
  HTTP `POST /` on 127.0.0.1:8799 → `notifications/claude/channel`, a `reply` tool that logs
  `REPLY chat_id=.. text=..` to `events.log`. Pure Node + `@modelcontextprotocol/sdk`.
- `pty_run.py` — launch harness: allocates a sized pty (`TIOCSWINSZ` 200x50) so the TUI
  initializes, keeps the master open so stdin never EOFs, streams the TUI to `chan.log`, and
  auto-sends Enter to confirm the `--dangerously-load-development-channels` warning dialog.
- `.mcp.json` registers the `webhook` server; `.claude/settings.json` sets
  `enableAllProjectMcpServers`; workspace trust pre-accepted in `~/.claude.json`.

## Steps (executed)
1. Ship harness, `npm i @modelcontextprotocol/sdk`. ✓
2. Launch detached, no TTY. Iterated on launch form:
   - plain interactive + `</dev/null` → auto-`--print`, errors "Input must be provided", exits. ✗
   - `-p "prompt"` → runs one turn, **exits** (print-and-exit). ✗
   - `-p --input-format stream-json` → **stays alive** but channel push does **not** fire a turn. ✗
   - `script` pty → TUI blank (no size/termios). ✗
   - **Python sized pty + auto-confirm Enter → TUI initializes, channel loads, session idles.** ✓
3. Push `POST /` with a unique-token instruction.
4. Confirm an autonomous turn fires the `reply` tool with the exact token; process stays alive.
5. Idle ≥5 min, push again, confirm still alive + still fires.

## Pass criteria
Headless no-TTY session stays alive idle AND autonomously replies (tool call) with the exact
token on push, twice (immediate + after ≥5 min idle).

## Key findings (feed Phase 10/11/13)
- **Interactive mode only** — channels fire turns in interactive sessions, NOT under `-p`
  (print) or `-p --input-format stream-json`. Production responder must run interactive.
- **Headless needs a real sized pty** — `script` is insufficient; a Python `openpty` +
  `TIOCSWINSZ` harness works (no tmux/screen on OpenClaw). This becomes the launch vehicle.
- **`--dangerously-load-development-channels` shows a confirm dialog** every launch → must
  auto-confirm (pty Enter) OR allowlist the bridge as a plugin via `allowedChannelPlugins`
  to use plain `--channels` (no prompt). Decide in Phase 11.
- **Workspace trust** must be pre-accepted (`hasTrustDialogAccepted` in `~/.claude.json`).
- **Cost:** every channel turn is a full Opus 4.8 (1M-context) turn (~$0.10+/turn observed).
  Real per-message cost for the responder — flag in Phase 13 / ops notes.
