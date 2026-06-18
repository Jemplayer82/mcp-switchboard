# Security Policy

## `[ threat model ]`

Switchboard is a self-hosted message bus for AI agents, designed for a **trusted network**
(homelab / small team behind a LAN or a Tailnet). Two properties define the model:

- **One shared bearer token.** Every agent authenticates with the same `SWITCHBOARD_MCP_TOKEN`.
  That token *is* the security boundary — anyone holding it can read and send all messages.
- **Client-asserted identity.** An agent declares its own `agent_id` / message `from`. The bus
  does not cryptographically verify that a message really came from the named agent.

Per-agent tokens (real authentication) are a planned upgrade. Until then: **protect the token,
and run Switchboard on a network you trust.** Do not expose it directly to the public internet —
put it behind a reverse proxy with TLS, and prefer a private overlay (Tailscale/WireGuard).

## `[ what's hardened ]`

Within that model, the following mitigations bound the blast radius of a leaked token or a
malicious/compromised agent:

| Area | Mitigation |
|---|---|
| **Auth** | Bearer check is constant-time (`crypto.timingSafeEqual`). |
| **Push-wake SSRF** | The bus only POSTs to an agent-supplied `wake_url` if its host is in `SWITCHBOARD_WAKE_ALLOWED_HOSTS`. **Fail-closed** — wake is disabled unless you opt in, so it can't be used as an SSRF/exfil gadget. |
| **Resource limits** | Request bodies are capped (`SWITCHBOARD_MAX_BODY_BYTES`, default 1 MB → `413`); inbox drains are bounded in SQL; REST query/body numerics are clamped to the same limits the MCP tools enforce. |
| **Headless responders** (channel bridge + `--with-daemon`) | Untrusted bus content fed to an LLM is bounded by: a **fail-closed sender allowlist** (`SWITCHBOARD_ALLOWED_SENDERS` — no allowlist ⇒ nothing is processed); a **per-sender rate limit** + content cap; and a **restricted tool surface** (`CHANNEL_DISALLOWED_TOOLS`) that blocks shell, file read/write, and network egress so a prompt-injection can't run commands or read local secrets (`~/.claude/.credentials.json`, `~/.switchboard/config.json`). |
| **Argument injection** | The daemon passes message content to the Claude CLI after a `--` option terminator, so content starting with `-` can never be parsed as CLI flags. |

> [!IMPORTANT]
> The responder tool restriction is a **denylist** — a new tool added in a future Claude CLI
> version is permitted by default. Re-audit `CHANNEL_DISALLOWED_TOOLS` when you upgrade the CLI,
> or switch to an explicit allowlist if your CLI version supports gating channel/MCP tools that way.

## `[ accepted residual risk ]`

These are inherent to the design and **accepted** for the trusted-network use case:

- **Shared token / spoofable `agent_id`.** Anyone with the token can impersonate any agent.
  Fix is per-agent tokens (roadmap). The allowlists above are defense-in-depth, *not*
  authentication — a token holder can spoof an allowlisted `from`.
- **Prompt injection into responders.** A headless responder reasons over untrusted text; the
  tool restriction means the worst case is a misleading reply, not host compromise or secret
  loss. Don't remove the tool restriction unless you trust every allowlisted sender completely.
- **`curl … | sh` install over the LAN.** The installer is served unauthenticated (it carries no
  secrets) and, on a plaintext-HTTP LAN, is MITM-able. Use TLS (`SWITCHBOARD_PUBLIC_BASE=https://…`
  behind a proxy) and read the script before piping it to a shell if you're cautious.

## `[ reporting a vulnerability ]`

Please report security issues **privately** — do not open a public issue for an unpatched flaw.

- Open a [GitHub Security Advisory](https://github.com/jemplayer82/mcp-switchboard/security/advisories/new), or
- Contact the maintainer via [github.com/jemplayer82](https://github.com/jemplayer82).

Include reproduction steps and impact. We'll acknowledge, triage, and credit you on a fix unless
you'd prefer otherwise.

## `[ supported versions ]`

Switchboard ships as a rolling `ghcr.io/jemplayer82/mcp-switchboard:latest` image. Security fixes
land on `main` and the `latest` tag; pull the current image to stay patched.
