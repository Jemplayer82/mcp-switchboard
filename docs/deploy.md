# `[ deploy ]`

Part of the [mcp-switchboard](../README.md) docs.

![image](https://img.shields.io/badge/image-ghcr.io-6cd5e6?style=flat-square&labelColor=030d14&logo=docker&logoColor=6cd5e6)

## `[ deploy · docker compose ]`

The repo ships a ready-to-run [`docker-compose.yaml`](../docker-compose.yaml). Everything is env-driven via `.env` (all optional — see [`.env.example`](../.env.example)):

| Variable | Default | Purpose |
| --- | --- | --- |
| `SWITCHBOARD_MCP_TOKEN` | *auto-generated* | Bearer token every agent uses. Unset → generated on first boot, persisted to `/data`, printed in logs. |
| `SWITCHBOARD_PORT` | `3107` | Host port to publish (container always listens on 3107). |
| `SWITCHBOARD_PUBLIC_BASE` | *Host header* | Public URL agents reach you on. Only needed behind a reverse proxy / custom domain; otherwise auto-detected per request. |
| `SWITCHBOARD_WAKE_ALLOWED_HOSTS` | *unset (wake disabled)* | Comma-separated `host` or `host:port` allowlist for push-wake `wake_url` targets — SSRF guard, fail-closed. See [honest limitations](how-it-works.md). |
| `SWITCHBOARD_MAX_BODY_BYTES` | `1000000` | Max request body size in bytes (oversized-POST guard). |

```bash
$ cp .env.example .env      # optional — edit to pin a token / port / domain
$ docker compose up -d
```

> [!TIP]
> Running behind a TLS reverse proxy or custom domain? Set `SWITCHBOARD_PUBLIC_BASE=https://switchboard.example.com` so the served install one-liner targets the public URL instead of the internal Host header.

> [!IMPORTANT]
> If you pin `SWITCHBOARD_MCP_TOKEN` yourself, set it in `.env` or the environment — **never commit it.**

## `[ portainer deployment ]`

The prebuilt image is published to `ghcr.io/jemplayer82/mcp-switchboard:latest` by GitHub Actions on every push to `main`. Deploy via Portainer as a standalone stack using the compose file above. Set `SWITCHBOARD_MCP_TOKEN` in the Portainer stack environment — not in the committed compose file.

After a fresh CI build, force-pull the latest image before redeploying:

```bash
$ docker compose pull && docker compose up -d
```

> [!WARNING]
> Portainer's `GET /api/stacks/<id>` returns `Env: []` (secrets redacted). If you PUT that empty array back, it **wipes** the environment variables. Always re-supply the full `Env` array on any stack update.

