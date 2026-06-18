# SECURITY.md — v1.2 Channel Responder (SEC-02)

> [!WARNING]
> **Post-review correction (pre-public-release audit).** This document originally claimed T4
> (secret exfiltration) was mitigated because M1 left "no file/Bash tools." That was inaccurate:
> the implemented restriction was a denylist of `Bash Edit Write MultiEdit NotebookEdit` only —
> **`Read`, `Glob`, `Grep`, and `WebFetch` were still enabled**, so an injection could read
> `~/.claude/.credentials.json` and exfiltrate via the reply tool or WebFetch. Fixed: the denylist
> now also covers `Read Glob Grep WebFetch WebSearch Task` (channel bridge, cold daemon, and both
> systemd units). A full-codebase review also added: push-wake SSRF guard, request/drain bounds,
> constant-time auth, REST input clamping, and cold-daemon hardening (fail-closed allowlist, rate
> limit, tool restriction, `--` argument-injection fix). See the top-level `SECURITY.md` for the
> current consolidated threat model. This file is retained as the point-in-time SEC-02 record.

**Scope:** the channel-injection path into the headless `Billy` responder — a persistent
`claude --channels` session on OpenClaw running with `--dangerously-skip-permissions`, fed by
arbitrary agent-bus message content via the `switchboard-channel` bridge.

**Trust model (baseline):** single shared `SWITCHBOARD_MCP_TOKEN` on a trusted LAN;
`agent_id` is **client-asserted** (the bus does not authenticate that a message's `from` is
really that agent). Anyone holding the bus token can assert any `from`.

## Threats, severity, disposition

| # | Threat | Severity | Disposition |
|---|--------|----------|-------------|
| T1 | **Prompt injection via message content** → crafted bus text drives Billy to run tools/exfiltrate, executed without confirmation due to `--dangerously-skip-permissions` | **High** | **Mitigated** (tool surface restricted + rate limit + hardened instructions) + residual **accepted** |
| T2 | **Allowlist bypass via spoofed `from`** — `send_message` accepts any `from`; an attacker with the bus token sends `from:"Claude"` and passes the allowlist | Medium | **Accepted** (trusted-LAN shared-token model; real fix = per-agent tokens, v2 SEC-01) |
| T3 | **Tool-abuse blast radius** under bypassed permissions = whatever user `landon` can do (read `~/.claude/.credentials.json` OAuth, `~/.switchboard/config.json` token, ssh keys; arbitrary commands) | **High** | **Mitigated** (restricted `--allowedTools`; see M1) |
| T4 | **Secret exfiltration** — injection reads OAuth/bus-token files and returns them via the reply tool | **High** | **Mitigated** by M1 (no file/Bash tools) + M3 |
| T5 | **Cost / DoS** — each injected message = one Opus turn (~$0.10+); a flood drains quota/credits | Medium | **Mitigated** (bridge rate-limit M2) |
| T6 | Research-preview `--dangerously-load-development-channels` (unreviewed flag) | Low | **Accepted** (self-hosted, trusted host) |

## Mitigations

- **M1 (primary) — restrict the responder's tool surface.** Launch the responder session with
  an explicit `--allowedTools` that excludes `Bash`, `Write`, `Edit` and file access, leaving the
  `switchboard reply` tool (+ any read-only tools you choose). This bounds blast radius even
  under successful prompt injection: Billy can reason and reply, but cannot run shell commands,
  write files, or read local secrets. **Trade-off:** Billy becomes a reason-and-reply agent, not
  an actuator. (Toggle in the unit; default ON for safety. Opt back into tools deliberately.)
- **M2 — bridge rate limit + content cap.** The bridge drops/queues messages above a per-sender
  rate and truncates oversized content before injection — caps cost/DoS and giant-payload abuse.
- **M3 — hardened channel instructions.** The bridge's `instructions` tell Billy that bus
  message content is **untrusted input from other agents**, to never reveal credentials/tokens
  or run destructive actions on their say-so, and to treat embedded "instructions" as data.

## Accepted residual risk
- T2 (spoofed `from`) and the trusted-LAN shared-token model are accepted for v1.2. The
  durable fix is per-agent bearer tokens (**v2 SEC-01**). Until then, the bus token is the real
  security boundary — protect it; anyone with it can drive Billy within M1's bounds.
- With M1 in place, the worst case of a successful injection is a misleading bus reply, not host
  compromise or secret loss.

## Verdict
With M1–M3 applied, the High-severity host-compromise / exfiltration paths (T1, T3, T4) are
reduced to Low residual; cost/DoS (T5) is bounded; identity-spoofing (T2) is explicitly accepted
pending per-agent tokens. **SEC-02 closed: mitigated or accepted.**
