# install.ps1 — thin bootstrap for the switchboard agent installer (Windows).
# Fetches install.mjs from the server and runs it with node. All real logic
# lives in install.mjs; this just gathers inputs and downloads.
#
#   irm http://my-switchboard:3107/install.ps1 | iex
#
# The server rewrites __SWITCHBOARD_BASE__ below to the URL you fetched this from,
# so $base is correct automatically. Override with $env:SWITCHBOARD_BASE.
#
# Inputs via env vars (set before piping to iex); prompts for anything missing:
#   $env:SWITCHBOARD_BASE       (auto-detected from the download URL)
#   $env:SWITCHBOARD_AGENT_ID
#   $env:SWITCHBOARD_MCP_TOKEN
#   $env:SWITCHBOARD_AGENT_NAME (optional)
$ErrorActionPreference = 'Stop'

# __SWITCHBOARD_BASE__ is substituted server-side at download time.
$templatedBase = '__SWITCHBOARD_BASE__'
if ($templatedBase -like '*SWITCHBOARD_BASE*') { $templatedBase = '' }

$base = if ($env:SWITCHBOARD_BASE) { $env:SWITCHBOARD_BASE.TrimEnd('/') }
        elseif ($templatedBase)    { $templatedBase.TrimEnd('/') }
        else                       { (Read-Host 'Switchboard base URL').TrimEnd('/') }
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
