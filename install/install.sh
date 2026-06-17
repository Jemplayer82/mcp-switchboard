#!/usr/bin/env sh
# install.sh — thin bootstrap for the switchboard agent installer.
# Fetches install.mjs from the server and runs it with node. All real logic
# lives in install.mjs; this just gathers inputs and downloads.
#
#   curl -fsSL http://my-switchboard:3107/install.sh | sh
#   curl -fsSL http://my-switchboard:3107/install.sh | sh -s -- --agent-id billy --with-daemon
#
# The server rewrites __SWITCHBOARD_BASE__ below to the URL you fetched this from,
# so BASE is correct automatically. Override with SWITCHBOARD_BASE / --base.
#
# Inputs via env (SWITCHBOARD_BASE / SWITCHBOARD_AGENT_ID / SWITCHBOARD_MCP_TOKEN)
# or flags; prompts for agent-id/token (and base, if not templated) if missing.
set -e

# __SWITCHBOARD_BASE__ is substituted server-side at download time.
TEMPLATED_BASE="__SWITCHBOARD_BASE__"
case "$TEMPLATED_BASE" in *SWITCHBOARD_BASE*) TEMPLATED_BASE="" ;; esac
BASE="${SWITCHBOARD_BASE:-$TEMPLATED_BASE}"
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
if [ -z "$BASE" ];     then printf "Switchboard base URL: " > /dev/tty; read BASE < /dev/tty; BASE="${BASE%/}"; fi
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
