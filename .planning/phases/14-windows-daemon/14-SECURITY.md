---
phase: 14
name: "Windows always-on presence daemon"
date: 2026-06-29
verdict: CLOSED
asvs_level: 1
auditor: retroactive-STRIDE
---

# SECURITY.md — Phase 14: Windows always-on presence daemon

**Scope:** `windows/windows-daemon.py` — the AtLogOn Windows presence daemon that keeps the
"Claude" agent registered on the bus, fires toast notifications on inbound DMs, and auto-replies
headlessly via `claude --print`. Extends the top-level `SECURITY.md` headless-responders section
to cover the Windows `--print` path specifically (complementing the Linux systemd cold-daemon and
Billy channel-bridge paths already covered there).

**Trust model (baseline):** single shared `SWITCHBOARD_MCP_TOKEN` on a trusted LAN; `agent_id`
is client-asserted (the bus does not cryptographically verify a message's `from`). This is the
same baseline as all other switchboard components.

**Register authored:** retroactively, post-implementation (no PLAN.md existed for this phase).

---

## Threat Register

| # | STRIDE | Component | Threat | Severity | Disposition | Status |
|---|--------|-----------|--------|----------|-------------|--------|
| TW1 | Spoofing | Bus protocol | Spoofed `from` passes allowlist — bus token holder sends DM as allowlisted agent | Medium | Accepted | CLOSED |
| TW2 | Info Disclosure | Toast | First 120 chars of attacker content shown on operator screen | Low | Accepted | CLOSED |
| TW3 | EoP | `toast()` / `_PS_TOAST` | PowerShell `@"..."@` here-string expands `$` and `$(expr)`; `_xml_escape()` only escapes XML metacharacters, not `$`; allowlisted sender sends `$(calc.exe)` and PowerShell executes it as operator | HIGH | **Fixed** | CLOSED |
| TW4 | Tampering | `interactive.lock` | Local attacker writes lock to suppress daemon or force double-drain | Low | Accepted | CLOSED |
| TW5 | DoS | Poll loop | 180s LLM call serializes processing; rate-limited messages accumulate | Medium | Accepted | CLOSED |
| TW6 | EoP | `run_claude` | `--disallowedTools` denylist permits new future tools by default | Medium | Accepted | CLOSED |
| TW7 | Info Disclosure | Config | `~/.switchboard/config.json` holds bearer token, world-readable | Low | Accepted | CLOSED |

**Threats open:** 0 / 7

---

## Threat Verification

### TW1 — Spoofing / Accepted
Shared-token / spoofable-`from` model is accepted and documented in the top-level `SECURITY.md`
under "accepted residual risk." The allowlist at `windows-daemon.py:341` is defense-in-depth, not
authentication. Accepted entry present in top-level `SECURITY.md`. **CLOSED.**

### TW2 — Info Disclosure / Accepted
`toast()` at line 270 passes `content[:120]` to the toast; the operator screen displays it.
Accepted because an attacker needs the bus token first (trusted-LAN model), and the toast display
is intentional operator UX. Accepted entry present in top-level `SECURITY.md`. **CLOSED.**

### TW3 — EoP / FIXED
**Root cause confirmed:** `_PS_TOAST` used a double-quoted PowerShell here-string (`@"..."@`),
which expands `$var` and `$(subexpr)` at evaluation time. `_xml_escape()` escapes XML
metacharacters (`&<>"'`) but does not escape `$`, leaving `$(calc.exe)` or arbitrary subexpressions
executable by PowerShell as the operator user.

**Fix applied** to `windows/windows-daemon.py`:
- Changed `$xml = @"` to `$xml = @'` (double-quoted → single-quoted here-string).
- Changed closing `"@` to `'@`, verified at column 0 (PowerShell syntax requirement).
- Added inline comment explaining why single-quote is required (TW3 mitigation note).

Single-quoted here-strings in PowerShell are completely literal — no variable expansion, no
subexpression expansion. Python `.replace("__SENDER__", ...)` and `.replace("__SNIPPET__", ...)`
execute in Python before the script is piped to PowerShell, so the substituted values are already
plain text by the time PowerShell sees them. `_xml_escape()` still runs and XML-encodes the values
before substitution, providing defense-in-depth against XML injection in the toast XML document.

**Verification:** `grep` confirms `$xml = @'` and `'@` at lines 250 and 255 respectively, both
at column 0. No `@"` or `"@` remains in `_PS_TOAST`. **CLOSED.**

### TW4 — Tampering / Accepted
`interactive.lock` is a local file. Manipulation requires local access to the operator machine,
which is outside the threat model (trusted-host). Accepted. **CLOSED.**

### TW5 — DoS / Accepted
`reply_timeout_sec=180` caps individual LLM calls. The in-process rate limiter (`rate_ok()`,
lines 319-328) caps per-sender message volume. Serial processing without multi-threading is an
accepted architectural trade-off given the solo-operator use case. **CLOSED.**

### TW6 — EoP / Accepted
`--disallowedTools` denylist (`Bash Edit Write MultiEdit NotebookEdit Read Glob Grep WebFetch
WebSearch Task`, lines 99-101) is acknowledged as permissive-by-default for future tools. This is
documented in the top-level `SECURITY.md` with a re-audit note for CLI upgrades. **CLOSED.**

### TW7 — Info Disclosure / Accepted
`~/.switchboard/config.json` contains the bearer token and has default filesystem permissions.
Accepted under the trusted-host model; the token is equivalent to shell access on a single-user
Windows workstation. **CLOSED.**

---

## Mitigations in Place

| Guard | Location | Detail |
|---|---|---|
| Fail-closed allowlist | `handle_message():341` | Empty allowlist drops all messages; must be set deliberately to enable responses. |
| Single-quoted PS here-string | `_PS_TOAST:250-255` | No PowerShell variable or subexpression expansion; blocks `$(cmd)`-style injection. **TW3 fix.** |
| XML escaping | `_xml_escape():266-269` | Sender and snippet are XML-escaped before substitution; defends toast XML document integrity. |
| Stdin-only content delivery | `toast():279` | PowerShell receives content on stdin (`-Command -`), never on the command line; no shell-metachar exposure. |
| `--strict-mcp-config` | `run_claude():293` | Claude CLI loads zero MCP servers; prevents switchboard recursion and docker-MCP-leak. |
| `--disallowedTools` | `run_claude():288` | Blocks shell, file I/O, and network tools from untrusted bus content. |
| `--` flag terminator | `run_claude():295` | Message content follows `--`; cannot be parsed as CLI flags. |
| Per-sender rate limiter | `rate_ok():319-328` | 20 messages per 60-second window (configurable) bounds DoS from a single sender. |
| 180s reply timeout | `run_claude():307` | Caps LLM call duration; subprocess is killed if exceeded. |
| Peek-then-claim ordering | `handle_message():362-368` | Message is claimed before LLM call; prevents double-processing if a session opens mid-reply. |
| Inbox yield to interactive session | `lock_fresh():231-236` | Daemon yields inbox when `interactive.lock` is fresh (< 90s), preventing collision with live sessions. |

---

## Accepted Residual Risks

| Risk | Basis for Acceptance |
|---|---|
| TW1: Spoofed `from` bypasses allowlist | Shared-token model; anyone with the token can assert any `from`. Per-agent tokens are the roadmap fix. Documented in top-level SECURITY.md. |
| TW2: Toast displays attacker content | Operator sees first 120 chars. Requires bus token (trusted-LAN boundary). Intentional UX feature. |
| TW4: Lock file manipulation | Requires local machine access. Trusted-host model. Worst case: daemon double-answers or goes silent temporarily. |
| TW5: Serial LLM processing | Architecture trade-off for solo operator. Rate limiter and 180s timeout bound abuse. |
| TW6: Denylist permissive for future tools | Documented. Re-audit required on Claude CLI upgrades. |
| TW7: Config token world-readable | Trusted-host model. Token = local machine access on a single-user workstation. |

---

## Extension to Top-Level SECURITY.md

The top-level `SECURITY.md` headless-responders section covers the channel bridge (`Billy`) and
the cold Linux daemon. This phase documents the same threat model applied to the **Windows
`--print` path**:

- The Windows daemon uses `claude --print` (stateless, one-shot) rather than a persistent
  `--channels` session. The tool restriction and `--strict-mcp-config` mitigations are identical.
- The Windows daemon adds a **toast notification path** not present in the Linux daemon; TW3
  (PowerShell injection) is specific to this path and is now mitigated by the single-quoted
  here-string fix.
- The Windows daemon adds the **`interactive.lock` yield mechanism** to coexist with a live
  Claude Code session on the same machine. This is not present in the Linux daemon.

No changes to the top-level `SECURITY.md` are required; this document extends it.

---

## Verdict

**CLOSED.** All 7 threats resolved: TW3 (HIGH) fixed by converting `_PS_TOAST` to a
single-quoted PowerShell here-string; TW1, TW2, TW4, TW5, TW6, TW7 accepted with documented
rationale under the trusted-LAN / trusted-host model. No unregistered threat flags identified
during implementation review.
