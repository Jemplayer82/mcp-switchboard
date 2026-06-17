# Phase 9 Summary: Headless Channel Spike

**Result:** ✅ GO — headless `claude --channels` is viable as a persistent full-context bus responder.

## What was proven (on OpenClaw, `claude` 2.1.179, real hardware)
A headless, no-TTY, detached `claude --channels` session **stays alive while idle** and
**autonomously fires a turn — including an MCP tool call — on a pushed channel event**, with
no human interaction:

| Event | Time (UTC) | Latency |
|-------|-----------|---------|
| PUSH #1 → autonomous `reply` `PONG-7F3A9` | 03:32:40 → 03:32:49 | ~9s |
| **6.5 min idle**, PUSH #2 → autonomous `reply` `LONGEVITY-Q9Z` | 03:39:05 → 03:39:09 | ~4s |

Process stayed alive throughout and after both. Exact unique tokens confirm it was the live
session reasoning, not an echo.

## The working launch recipe (5 forms tried; only the last works)
| Form | Outcome |
|------|---------|
| interactive + `</dev/null` | auto-`--print`, "Input must be provided", exits ✗ |
| `-p "prompt"` | one turn, then exits ✗ |
| `-p --input-format stream-json` | stays alive, but channel push does **not** fire a turn ✗ |
| `script` pty | TUI blank (no size/termios) ✗ |
| **Python `openpty` + `TIOCSWINSZ` (sized pty) + auto-confirm Enter + pre-accepted trust** | ✅ TUI init, channel loads, idles, fires on push |

## Six sub-questions (answered)
1. `--channels` on 2.1.179 — **yes** (via `--dangerously-load-development-channels` for custom).
2. Headless no-TTY survival — **yes**, with a sized pty harness (not `script`).
3. Autonomous turn on push — **yes** (tool call, exact token).
4. ≥5 min idle longevity — **yes** (fired after 6.5 min idle, still alive).
5. OAuth scope adequate — **yes** (channel delivery succeeded; full-scope claude.ai OAuth).
6. Compaction viability — **deferred to Phase 12**; hourly session rotation is the safe fallback.

## Findings that constrain Phases 10–13
- **Interactive mode only** — channels do NOT fire turns under `-p` / stream-json. Responder must run interactive.
- **Sized pty required** — `run-channel-session.py` (Python `openpty`+`TIOCSWINSZ`) is the launch vehicle; no tmux/screen on OpenClaw.
- **Dev-channels confirm dialog** — `--dangerously-load-development-channels` prompts every launch; auto-confirmed via a pty Enter. Alternative: allowlist the bridge as a plugin (`allowedChannelPlugins`) to use plain `--channels` (no prompt) — Phase 11 decision.
- **Workspace trust** — must be pre-accepted (`hasTrustDialogAccepted` in `~/.claude.json`).
- **Inbox-drain collision** — OpenClaw's bus identity is **Billy** (the cold `claude-code-agent` daemon registers as Billy; the spike session also surfaced as Billy/`[chan-spike]`). Phase 11 must make the responder the SOLE consumer of Billy's inbox — i.e., retire `claude-code-agent` and run the channel responder under `Billy`.
- **Cost** — every channel turn is a full Opus-4.8 (1M-context) turn (~$0.10+/turn). Real per-message cost; flag in Phase 13 / ops.

## Artifacts (staged for Phase 10/11, in C:\tmp)
`switchboard-channel.mjs` (bridge), `run-channel-session.py` (pty harness), `claude-channel-agent.service` (unit).
Spike harness on OpenClaw `~/chan-spike/` torn down after the run.
