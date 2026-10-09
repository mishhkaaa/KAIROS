# Stops the console and kairosd windows started by these scripts. -All also stops Ollama (and its runners) and the
# compose containers; containers started some other way are left alone.
param([switch]$All)
. "$PSScriptRoot\common.ps1"
Set-Location $Repo
Stop-OwnWindow $ConsolePort "start-console.ps1" | Out-Null
Stop-OwnWindow $GatewayPort "start-kairosd.ps1" | Out-Null
if ($All) {
  Get-Process "ollama app", "ollama", "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
  "stopped Ollama"
  docker compose -f infra/compose/docker-compose.yml stop 2>&1 | Where-Object { $_ -match "Stopped|Error" }
}
"KAIROS stopped"
