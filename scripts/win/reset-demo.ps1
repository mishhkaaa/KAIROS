# Before each rehearsal (DEMO_SCRIPT QA checklist): restart kairosd (resets the in-process mock Jira), empty memories
# and working sets in the demo database, restart the kairosd window, warm the models, run the preflight.
param([switch]$SkipPreflight)
. "$PSScriptRoot\common.ps1"
Set-Location $Repo
Stop-OwnWindow $GatewayPort "start-kairosd.ps1" | Out-Null
$env:PYTHONIOENCODING = "utf-8"
uv run python -c "import sys, psycopg; c = psycopg.connect(sys.argv[1].replace('+psycopg', ''), autocommit=True); c.execute('TRUNCATE memories, working_sets'); print('memories and working sets emptied')" $DemoDatabaseUrl
Start-Window "start-kairosd.ps1"
if (-not (Wait-Http "$Gateway/system/status" 120)) { Write-Error "kairosd didn't come up; see .data/logs/kairosd.log"; exit 1 }
"kairosd up on :$GatewayPort"
if (-not $SkipPreflight) { uv run python scripts/preflight.py --gateway $Gateway }
