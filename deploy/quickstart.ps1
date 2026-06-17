# quickstart.ps1 — stand up a self-hosted switchboard in one command (Windows).
# Run from the repo root (it uses docker-compose.yaml):
#   .\deploy\quickstart.ps1
#
# Generates a token if you don't have one, brings the stack up, waits for it to
# go healthy, and prints the one-liner your agents use to wire themselves in.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

# --- preflight ----------------------------------------------------------------
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'docker is required but not found in PATH' }

$port = if ($env:SWITCHBOARD_PORT) { $env:SWITCHBOARD_PORT } else { '3107' }

# --- token --------------------------------------------------------------------
$token = $env:SWITCHBOARD_MCP_TOKEN
if (-not $token -and (Test-Path .env)) {
  $line = Select-String -Path .env -Pattern '^SWITCHBOARD_MCP_TOKEN=(.+)$' | Select-Object -First 1
  if ($line) { $token = $line.Matches[0].Groups[1].Value }
}
if (-not $token) {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $token = -join ($bytes | ForEach-Object { $_.ToString('x2') })
  if (-not (Test-Path .env)) { if (Test-Path .env.example) { Copy-Item .env.example .env } else { New-Item -ItemType File .env | Out-Null } }
  (Get-Content .env | Where-Object { $_ -notmatch '^\s*#?\s*SWITCHBOARD_MCP_TOKEN=' }) | Set-Content .env
  Add-Content .env "SWITCHBOARD_MCP_TOKEN=$token"
  Write-Host '-> generated a token and wrote it to .env'
}

# --- up -----------------------------------------------------------------------
Write-Host '-> pulling image and starting the switchboard...'
docker compose pull
docker compose up -d

# --- wait for healthy ---------------------------------------------------------
Write-Host "-> waiting for healthz on :$port " -NoNewline
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
  try { Invoke-WebRequest "http://localhost:$port/healthz" -UseBasicParsing -TimeoutSec 2 | Out-Null; $ok = $true; break }
  catch { Write-Host '.' -NoNewline; Start-Sleep 1 }
}
if (-not $ok) { Write-Host ' timed out'; Write-Host 'Check: docker compose logs switchboard'; exit 1 }
Write-Host ' ok'

# --- report -------------------------------------------------------------------
$ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
       Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
       Select-Object -First 1).IPAddress
if (-not $ip) { $ip = 'localhost' }
$base = "http://${ip}:$port"

Write-Host ''
Write-Host '================================================================'
Write-Host "  Switchboard is up at $base"
Write-Host "  Token: $token"
Write-Host ''
Write-Host '  Wire an agent in (run on the agent''s host):'
Write-Host '    Linux/macOS:'
Write-Host "      curl -fsSL $base/install.sh | sh -s -- --agent-id myagent --token $token"
Write-Host '    Windows (PowerShell):'
Write-Host "      `$env:SWITCHBOARD_AGENT_ID='myagent'; `$env:SWITCHBOARD_MCP_TOKEN='$token'; irm $base/install.ps1 | iex"
Write-Host '================================================================'
