# Differential Security Review — Phase 14 Windows Daemon (close-out)

**Scope:** commits `5f010b4` (PR #3, always-on Windows daemon) + `040677f` (cmd-window /
error-forwarding-loop fix), diffed against `8746533` (pre-session base).
**Strategy:** Quick triage (SMALL, 2 logic files, well-understood — author has direct
runtime evidence from same-session testing, not a cold review).

## Risk classification

| File | Risk | Why |
|---|---|---|
| `windows/windows-daemon.py` | HIGH | External calls (subprocess spawn from untrusted bus content), auth-adjacent (allowlist gate) |
| `windows/install-task.ps1` | LOW | Scheduling config only, no new input handling |
| `windows/README.md`, `windows/config.example.json`, `.planning/14-UAT.md` | LOW | Docs / placeholder config, no real credential |

## Blast radius

`windows-daemon.py` has one entry point (the daemon process) and one external effect
surface: `subprocess.run()` → `claude --print` with bus-supplied `content` as the final
argv element (after `--`). No other file in the repo imports or calls into this module —
blast radius is self-contained to this one process.

## Findings

**1. Alias-inbox mechanism does not weaken the allowlist gate.** `handle_message()`
line 386 (`sender not in CFG["allowlist"]`) checks `msg.get("from")`, which is fully
independent of which inbox (`Claude` vs `claude-code`) the message arrived on. A
non-allowlisted sender DMing the `claude-code` alias is dropped exactly like DMing
`Claude` directly. No new bypass introduced by polling multiple inboxes.

**2. `_inbox_id` cannot be attacker-influenced.** `peek_inbox()` sets
`m["_inbox_id"] = aid` where `aid` comes from the loop over `[CFG["agent_id"]] +
CFG["aliases"]` — a fixed, config-controlled list — and this assignment happens
*after* the message dict is parsed from the bus response, so it unconditionally
overwrites any pre-existing key. There's no path for message content to control which
cursor `ack()` advances.

**3. The `run_claude()` refactor is a hardening, not a regression.** Git history shows
no prior security-specific commit on this function — the old `stdout.strip() or
stderr.strip()` fallback was a plain bug (conflating success and failure), not a
security control being removed. The new version raises on nonzero exit and
`handle_message()` now logs-and-drops instead of ever forwarding subprocess
stdout/stderr to a message recipient on failure. This closes a real information/behavior
leak (raw CLI error text — observed in production this session as a self-sustaining
reply loop) rather than opening one.

**4. `creationflags=subprocess.CREATE_NO_WINDOW`** is a pure Windows console-visibility
flag; it does not suppress any prompt, elevation, or security dialog — confirmed no
functional/security change beyond hiding the window.

## Test coverage note

No automated test suite exists for this daemon (Python, no pytest/unittest present;
`package.json` only has `start`, no `test`). Verification for this change was live/manual:
syntax-checked (`py_compile`), daemon restarted and confirmed clean startup + empty
inbox + no errors in log, and the original failure mode (raw 401 forwarded as a reply)
was reproduced and re-verified fixed by direct observation of bus traffic going quiet
after the patch. This is flagged as tech debt, not a blocker — appropriate given the
project's existing test posture (no other component in this repo has an automated
suite either).

## Verdict

No security regressions found. No HIGH or MEDIUM findings. The diff is a net
hardening (closes an error-forwarding/info-leak path) plus a cosmetic UX fix
(console window suppression) plus an additive, allowlist-respecting alias feature.

**Coverage limits:** This is a quick-triage pass on a small, single-session diff by the
same author who wrote and live-tested it — not a cold independent audit. Full adversarial
modeling (Phase 5) was not run given the LOW/HIGH split above didn't surface anything
warranting it; a fresh pair of eyes via `security-review` ran in parallel to this pass
for independent coverage.
