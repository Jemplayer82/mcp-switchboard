#!/usr/bin/env sh
# install.sh — thin bootstrap for the switchboard agent installer.
# Fetches install.mjs from the server and runs it with node. All real logic
# lives in install.mjs; this just gathers inputs and downloads.
#
#   curl -fsSL http://192.168.7.50:3108/install.sh | sh
#   curl -fsSL http://192.168.7.50:3108/install.sh | sh -s -- --agent-id billy --with-daemon
#
# Inputs via env (SWITCHBOARD_BASE / SWITCHBOARD_AGENT_ID / SWITCHBOARD_MCP_TOKEN)
# or flags; prompts for agent-id/token if still missing.
set -e

BASE="${SWITCHBOARD_BASE:-http://192.168.7.50:3108}"
AGENT_ID="${SWITCHBOARD_AGENT_ID:-}"
TOKEN="${SWITCHBOARD_MCP_TOKEN:-}"
EXTRA=""

while [ $# -gt 0 ]; do
  case "$1" in
    --agent-id) AGENT_ID="$2"; shift 2 ;;
    --token)    TOKEN="$2";    shift 2 ;;
    --base)     BASE="$2";     shift 2 ;;
    *)          EXTRA="$EXTRA $1"; shift ;;
  esac
done

BASE="${BASE%/}"

# Read from the terminal, not the piped script, when run via `curl | sh`.
if [ -z "$AGENT_ID" ]; then printf "Agent id: " > /dev/tty; read AGENT_ID < /dev/tty; fi
if [ -z "$TOKEN" ];    then printf "Switchboard token: " > /dev/tty; read TOKEN < /dev/tty; fi

command -v node >/dev/null 2>&1 || { echo "✗ node is required but not found in PATH"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "✗ curl is required but not found in PATH"; exit 1; }

# Node infers ESM from the .mjs extension, so the temp file must keep it.
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT
TMP="$TMPD/install.mjs"
curl -fsSL "$BASE/install/install.mjs" -o "$TMP"
# shellcheck disable=SC2086
node "$TMP" --agent-id "$AGENT_ID" --token "$TOKEN" --base "$BASE" $EXTRA
