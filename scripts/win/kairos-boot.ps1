# "Boot into KAIROS": start whatever isn't running (Docker Desktop, Postgres/Redis/vendor-docs, Ollama with the chat
# model loaded, kairosd, the console), then open the /boot screen full-screen with no browser UI.
# Alt+F4 leaves kiosk mode. -NoKiosk opens a normal window instead; -NoBrowser starts everything and opens nothing.
param([switch]$NoKiosk, [switch]$NoBrowser)
. "$PSScriptRoot\common.ps1"
Set-Location $Repo

function Step([string]$Label) { Write-Host "-> $Label" -ForegroundColor Cyan }

Step "Docker"
docker info *> $null
if ($LASTEXITCODE -ne 0) {
  Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
  for ($i = 0; $i -lt 90; $i++) { docker info *> $null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep 2 }
  if ($LASTEXITCODE -ne 0) { Write-Error "Docker Desktop didn't start"; exit 1 }
}

Step "Postgres :$PgPort, Redis :$RedisPort, vendor-docs"
$env:KAIROS_PG_PORT = $PgPort; $env:KAIROS_REDIS_PORT = $RedisPort
$services = @()
if (-not (Test-Port $PgPort)) { $services += "postgres" }
if (-not (Test-Port $RedisPort)) { $services += "redis" }
$services += "vendor-docs"   # always: starting it creates the internal network the browser sandbox uses
docker compose -f infra/compose/docker-compose.yml up -d @services 2>&1 | Where-Object { $_ -match "Error|error" }

Step "Ollama + $ChatModel"
$runners = @(Get-Process llama-server -ErrorAction SilentlyContinue).Count
$loaded = $false
try { $loaded = [bool]((Invoke-RestMethod http://127.0.0.1:11434/api/ps -TimeoutSec 2).models | Where-Object name -eq $ChatModel) } catch {}
if (-not $loaded -or $runners -gt 2) { & "$PSScriptRoot\restart-ollama.ps1" | Select-Object -Last 4 }

Step "kairosd :$GatewayPort"
if (-not (Test-Port $GatewayPort)) { Start-Window "start-kairosd.ps1" }

Step "console :$ConsolePort"
if (-not (Test-Port $ConsolePort)) { Start-Window "start-console.ps1" }
if (-not (Wait-Http "http://127.0.0.1:$ConsolePort/" 300)) { Write-Error "the console didn't come up"; exit 1 }

$url = "http://localhost:$ConsolePort/boot"
if ($NoBrowser) { "KAIROS is up: $url"; exit 0 }
Step "opening $url"
$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($NoKiosk) { Start-Process $url }
elseif ($edge) { Start-Process $edge -ArgumentList "--kiosk", $url, "--edge-kiosk-type=fullscreen", "--no-first-run" }
elseif ($chrome) { Start-Process $chrome -ArgumentList "--kiosk", $url, "--no-first-run" }
else { Start-Process $url }
"KAIROS is booting. Alt+F4 leaves kiosk mode; scripts\win\kairos-shutdown.ps1 stops it."
