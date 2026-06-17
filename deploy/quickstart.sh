#!/usr/bin/env sh
# quickstart.sh — stand up a self-hosted switchboard in one command.
# Run from the repo root (it uses docker-compose.yaml):
#   ./deploy/quickstart.sh
#
# Generates a token if you don't have one, brings the stack up, waits for it to
# go healthy, and prints the one-liner your agents use to wire themselves in.
set -e

cd "$(dirname "$0")/.."

# --- preflight ----------------------------------------------------------------
command -v docker >/dev/null 2>&1 || { echo "✗ docker is required but not found in PATH"; exit 1; }
if docker compose version >/dev/null 2>&1; then DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"
else echo "✗ docker compose (v2) or docker-compose is required"; exit 1; fi

PORT="${SWITCHBOARD_PORT:-3107}"

# --- token --------------------------------------------------------------------
# Reuse an existing .env token; else generate one and write .env.
TOKEN="${SWITCHBOARD_MCP_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f .env ]; then
  TOKEN="$(grep -E '^SWITCHBOARD_MCP_TOKEN=' .env | head -1 | cut -d= -f2- || true)"
fi
if [ -z "$TOKEN" ]; then
  if command -v openssl >/dev/null 2>&1; then TOKEN="$(openssl rand -hex 32)"
  else TOKEN="$(head -c32 /dev/urandom | od -An -tx1 | tr -d ' \n')"; fi
  [ -f .env ] || { [ -f .env.example ] && cp .env.example .env || touch .env; }
  # strip any commented/blank token line, then append the real one
  grep -v -E '^#?\s*SWITCHBOARD_MCP_TOKEN=' .env > .env.tmp 2>/dev/null || true
  mv .env.tmp .env 2>/dev/null || true
  printf 'SWITCHBOARD_MCP_TOKEN=%s\n' "$TOKEN" >> .env
  echo "→ generated a token and wrote it to .env"
fi

# --- up -----------------------------------------------------------------------
echo "→ pulling image and starting the switchboard…"
$DC pull
$DC up -d

# --- wait for healthy ---------------------------------------------------------
printf "→ waiting for healthz on :%s " "$PORT"
i=0
until curl -sf "http://localhost:${PORT}/healthz" >/dev/null 2>&1; do
  i=$((i+1)); [ "$i" -gt 60 ] && { echo " timed out"; echo "Check: $DC logs switchboard"; exit 1; }
  printf "."; sleep 1
done
echo " ok"

# --- report -------------------------------------------------------------------
# Best-effort LAN IP for the agent one-liner (falls back to localhost).
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; [ -z "$IP" ] && IP="localhost"
BASE="http://${IP}:${PORT}"

echo
echo "================================================================"
echo "  Switchboard is up at ${BASE}"
echo "  Token: ${TOKEN}"
echo
echo "  Wire an agent in (run on the agent's host):"
echo "    Linux/macOS:"
echo "      curl -fsSL ${BASE}/install.sh | sh -s -- --agent-id myagent --token ${TOKEN}"
echo "    Windows (PowerShell):"
echo "      \$env:SWITCHBOARD_AGENT_ID='myagent'; \$env:SWITCHBOARD_MCP_TOKEN='${TOKEN}'; irm ${BASE}/install.ps1 | iex"
echo
echo "  Add --with-daemon (Linux) for a headless responder that answers"
echo "  even when no interactive session is open."
echo "================================================================"
