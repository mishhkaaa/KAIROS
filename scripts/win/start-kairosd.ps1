# Runs kairosd with the demo settings in this window; output is also written to
# .data/logs/kairosd.log. The demo database is set here only, so tests (via .env) keep using kairos_test.
. "$PSScriptRoot\common.ps1"
Set-Location $Repo
$env:KAIROS_DEFAULT_MODE = "real"
$env:KAIROS_OKF_DIR = "./data/okf"
$env:KAIROS_DATA_DIR = "./.data/demo"
$env:KAIROS_KNOWLEDGE_WATCH = "true"
$env:KAIROS_SANDBOX_ENDPOINT = "port"
$env:KAIROS_JIRA_URL = "inprocess"
$env:KAIROS_DATABASE_URL = $DemoDatabaseUrl
$env:KAIROS_REDIS_URL = $DemoRedisUrl
$env:KAIROS_DEMO_DATA_URL = $DemoDataUrl       # the db tool (scripts/seed_demo_data.py fills it)
$env:KAIROS_MODELS_CONFIG = $ModelsConfig
$env:KAIROS_GATEWAY_PORT = $GatewayPort
$env:KAIROS_URL = "http://localhost:$GatewayPort"
$env:PYTHONIOENCODING = "utf-8"
# Connector tokens are encrypted at rest with a key made on this machine on first start; it lives in .data (git-ignored)
# and never in the repo. Set KAIROS_VAULT_KEY yourself to use another.
if (-not $env:KAIROS_VAULT_KEY) {
    $keyFile = Join-Path $Repo ".data\vault.key"
    if (-not (Test-Path $keyFile)) {
        $bytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_") | Out-File -Encoding ascii -NoNewline $keyFile
    }
    $env:KAIROS_VAULT_KEY = (Get-Content $keyFile -Raw).Trim()
}
$Host.UI.RawUI.WindowTitle = "kairosd :$GatewayPort"
$log = Join-Path $Logs "kairosd.log"
"=== start $(Get-Date -Format s)" | Out-File -Encoding utf8 -Append $log
uv run kairosd 2>&1 | ForEach-Object { "$_"; "$_" | Out-File -Encoding utf8 -Append $log }
