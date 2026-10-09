# Serves the console's production build in this window. -Build rebuilds first (needed after a code change or when the
# gateway port changes: NEXT_PUBLIC_KAIROS_URL is baked in at build time).
param([switch]$Build)
. "$PSScriptRoot\common.ps1"
Set-Location (Join-Path $Repo "apps\web")
$Host.UI.RawUI.WindowTitle = "console :$ConsolePort"
$want = "NEXT_PUBLIC_KAIROS_URL=http://localhost:$GatewayPort"
if (-not (Test-Path .env.local) -or ((Get-Content .env.local -Raw) -notmatch [regex]::Escape($want))) {
  [IO.File]::WriteAllText("$PWD\.env.local", "$want`n")
  $Build = $true
}
$built = Get-Item .next\BUILD_ID -ErrorAction SilentlyContinue
$newer = if ($built) { Get-ChildItem app, components, lib, ..\..\shared\ts\src -Recurse -File | Where-Object LastWriteTime -gt $built.LastWriteTime | Select-Object -First 1 }
if ($Build -or -not $built -or $newer) {
  npm run build
  if ($LASTEXITCODE -ne 0) { Write-Error "console build failed"; exit 1 }
}
npx next start -p $ConsolePort
