# Lets a phone on the laptop's hotspot (or the same private Wi-Fi) open the console and approve from it.
# Prints the LAN URLs (console, and the server address the KAIROS phone app asks for) and a QR code, and opens the
# console and gateway ports in Windows Firewall for the Private profile only. Run as administrator. -Remove deletes the
# rules again; do that after the demo. In dev sign-in mode anyone who reaches the gateway is trusted: use your own
# hotspot, never a public network (KAIROS_AUTH=google requires a real sign-in).
param([switch]$Remove)
. "$PSScriptRoot\common.ps1"
$rule = "KAIROS (console + gateway, private network)"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Write-Error "Run this from an administrator PowerShell (the firewall rules need it)."; exit 1 }

if ($Remove) {
  Remove-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
  "removed the firewall rule '$rule'"
  exit 0
}

if (-not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName $rule -Direction Inbound -Protocol TCP -LocalPort $ConsolePort, $GatewayPort `
    -Profile Private -Action Allow | Out-Null
  "added firewall rule '$rule' (TCP $ConsolePort, $GatewayPort; Private profile only)"
}

# The hotspot adapter (192.168.137.x) first, then any other private IPv4 address on an adapter that's up.
$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -match '^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)' -and $_.InterfaceAlias -notmatch 'vEthernet|WSL|Docker|Loopback' } |
  Sort-Object @{ Expression = { $_.IPAddress -notlike '192.168.137.*' } }, InterfaceAlias
if (-not $ips) { Write-Error "no private network address found: turn on Mobile hotspot or join a private Wi-Fi"; exit 1 }

$profiles = Get-NetConnectionProfile -ErrorAction SilentlyContinue
foreach ($ip in $ips) {
  $p = ($profiles | Where-Object InterfaceIndex -eq $ip.InterfaceIndex).NetworkCategory
  "  {0,-28} http://{1}:{2}   ({3} network)" -f $ip.InterfaceAlias, $ip.IPAddress, $ConsolePort, $(if ($p) { $p } else { "hotspot" })
}
$url = "http://$($ips[0].IPAddress):$ConsolePort/approvals"
""
"Open on the phone: $url"
"KAIROS app server: http://$($ips[0].IPAddress):$GatewayPort   (then 'I have a code': make one in the console's user menu)"
Set-Location $Repo
uv run --quiet --with qrcode python -c "import qrcode, sys; q = qrcode.QRCode(border=1); q.add_data(sys.argv[1]); q.print_ascii(invert=True)" $url 2>$null
"If a network shows as Public, make it Private (Settings > Network) or the phone can't connect."
