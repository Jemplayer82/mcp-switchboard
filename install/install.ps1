# install.ps1 — thin bootstrap for the switchboard agent installer (Windows).
# Fetches install.mjs from the server and runs it with node. All real logic
# lives in install.mjs; this just gathers inputs and downloads.
#
#   irm http://192.168.7.50:3108/install.ps1 | iex
#
# Inputs via env vars (set before piping to iex); prompts for anything missing:
#   $env:SWITCHBOARD_BASE       (default http://192.168.7.50:3108)
#   $env:SWITCHBOARD_AGENT_ID
#   $env:SWITCHBOARD_MCP_TOKEN
#   $env:SWITCHBOARD_AGENT_NAME (optional)
$ErrorActionPreference = 'Stop'

$base    = if ($env:SWITCHBOARD_BASE)     { $env:SWITCHBOARD_BASE.TrimEnd('/') } else { 'http://192.168.7.50:3108' }
$agentId = if ($env:SWITCHBOARD_AGENT_ID) { $env:SWITCHBOARD_AGENT_ID } else { Read-Host 'Agent id' }
$token   = if ($env:SWITCHBOARD_MCP_TOKEN){ $env:SWITCHBOARD_MCP_TOKEN } else { Read-Host 'Switchboard token' }

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw 'node is required but not found in PATH'
}

$nodeArgs = @('--agent-id', $agentId, '--token', $token, '--base', $base)
if ($env:SWITCHBOARD_AGENT_NAME) { $nodeArgs += @('--name', $env:SWITCHBOARD_AGENT_NAME) }

$tmp = Join-Path $env:TEMP 'sb-install.mjs'
try {
  Invoke-WebRequest -Uri "$base/install/install.mjs" -OutFile $tmp -UseBasicParsing
  & node $tmp @nodeArgs
} finally {
  Remove-Item $tmp -ErrorAction SilentlyContinue
}
