# Creates "kairos-os": a WSL distro (Ubuntu 24.04) that is KAIROS's own Linux. /org in it is the organization's
# knowledge, served live by the gateway on this computer; `kairos` there asks, approves, searches, mounts folders.
# It is a separate distro: every other WSL distro on this machine is left exactly as it is.
#   powershell -File scripts\wsl\install-kairos-os.ps1              # create (or re-provision) and open instructions
#   powershell -File scripts\wsl\install-kairos-os.ps1 -Reinstall   # delete kairos-os and start over
#   wsl -d kairos-os                                                 # use it (also listed in Windows Terminal)
param([string]$Name = "kairos-os", [string]$Location = "$env:LOCALAPPDATA\KAIROS\wsl\kairos-os", [switch]$Reinstall)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$cache = Join-Path $Repo ".data\wsl"
$file = "ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz"
$base = "https://cloud-images.ubuntu.com/wsl/releases/24.04/current"
$rootfs = Join-Path $cache $file

function Distros { (wsl.exe -l -q) -replace "`0", "" | ForEach-Object { $_.Trim() } | Where-Object { $_ } }
$exists = (Distros) -contains $Name

if ($exists -and $Reinstall) {
    "removing the old $Name (only this distro)"
    wsl.exe --unregister $Name | Out-Null
    $exists = $false
}
if (-not $exists) {
    New-Item -ItemType Directory -Force $cache | Out-Null
    if (-not (Test-Path $rootfs)) {
        "downloading Ubuntu 24.04 for WSL (about 350 MB)"
        Invoke-WebRequest "$base/$file" -OutFile $rootfs -UseBasicParsing
    }
    $sums = (Invoke-WebRequest "$base/SHA256SUMS" -UseBasicParsing).Content -split "`n" | Where-Object { $_ -match [regex]::Escape($file) }
    $want = ($sums -split "\s+")[0]
    $have = (Get-FileHash $rootfs -Algorithm SHA256).Hash.ToLower()
    if ($want -and $have -ne $want.ToLower()) { Remove-Item $rootfs; throw "checksum mismatch for $file; deleted it, run again" }
    New-Item -ItemType Directory -Force $Location | Out-Null
    "importing $Name into $Location"
    wsl.exe --import $Name $Location $rootfs --version 2
    if ($LASTEXITCODE) { throw "wsl --import failed" }
}

# This repo's scripts/wsl/kairos-os as Linux sees it.
$src = Join-Path $PSScriptRoot "kairos-os"
$linux = "/mnt/" + $src.Substring(0, 1).ToLower() + ($src.Substring(2) -replace "\\", "/")

# apt downloads go through a relay on Windows (apt-proxy.py next to this script): some networks stall large packets on
# WSL's NAT path. It listens only on the WSL host address and stops when provisioning ends.
$hostIp = (wsl.exe -d $Name -u root -- sh -c "ip route show default | cut -d' ' -f3").Trim()
$port = 3142
$relay = Join-Path $PSScriptRoot "apt-proxy.py"
$proxy = Start-Process -FilePath "uv" -ArgumentList "run", "--project", "`"$Repo`"", "python", "`"$relay`"", $hostIp, $port `
    -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 4
"provisioning (packages, the kairos user, /org, the kairos command)"
try {
    wsl.exe -d $Name -u root -- env "APT_PROXY=http://${hostIp}:$port" bash "$linux/provision.sh" "$linux"
    if ($LASTEXITCODE) { throw "provisioning failed" }
} finally {
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$($proxy.Id)" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $proxy.Id -Force -ErrorAction SilentlyContinue
}
# Restart it so wsl.conf (systemd, the default user, the hostname) takes effect; only this distro stops.
wsl.exe --terminate $Name | Out-Null
""
"kairos-os is ready. Start kairosd on Windows (scripts\win\start-kairosd.ps1), then:"
"  wsl -d $Name                  # or pick it in Windows Terminal"
"  ls /org ; cat /org/finance/apollo-budget.md ; kairos ask `"Why is Apollo over budget?`""
