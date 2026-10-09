#!/bin/bash
# Provisions the kairos-os WSL distro (run as root by scripts/wsl/install-kairos-os.ps1). Idempotent.
#   $1: this folder as Linux sees it (/mnt/c/.../scripts/wsl/kairos-os)
#   APT_PROXY: the installer's relay through Windows, for networks that stall large packets inside WSL
set -euo pipefail
SRC="${1:?usage: provision.sh <path to scripts/wsl/kairos-os>}"
export DEBIAN_FRONTEND=noninteractive

# WSL's NAT network has no IPv6 route, and apt would hang on the mirrors' IPv6 addresses.
echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99kairos-ipv4
if [ -n "${APT_PROXY:-}" ]; then
  {
    echo "Acquire::http::Proxy \"$APT_PROXY\";"
    echo "Acquire::https::Proxy \"$APT_PROXY\";"
    echo 'Acquire::http::Pipeline-Depth "0";'
  } > /etc/apt/apt.conf.d/99kairos-proxy
fi
if ! dpkg -s python3-fusepy libfuse2t64 fuse3 >/dev/null 2>&1; then
  apt-get -o Acquire::http::Timeout=30 update -qq
  apt-get install -y -qq --no-install-recommends python3 python3-fusepy fuse3 libfuse2t64 iproute2 ca-certificates sudo less nano curl >/dev/null
fi
rm -f /etc/apt/apt.conf.d/99kairos-proxy

id kairos >/dev/null 2>&1 || useradd -m -s /bin/bash -G sudo -c "KAIROS" kairos
echo "kairos ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/kairos
chmod 0440 /etc/sudoers.d/kairos

install -d /opt/kairos /etc/kairos
install -m 0644 "$SRC/kairosos.py" /opt/kairos/kairosos.py
install -m 0755 "$SRC/orgfs.py" /opt/kairos/orgfs.py
install -m 0755 "$SRC/kairos" /usr/local/bin/kairos
install -m 0644 "$SRC/kairos-orgfs.service" /etc/systemd/system/kairos-orgfs.service
install -m 0644 "$SRC/profile.sh" /etc/profile.d/zz-kairos.sh
# Files checked out on Windows may carry CRLF endings.
sed -i 's/\r$//' /usr/local/bin/kairos /opt/kairos/*.py /etc/profile.d/zz-kairos.sh /etc/systemd/system/kairos-orgfs.service
install -d -o kairos -g kairos /org /home/kairos/.config /home/kairos/.config/kairos
[ -f /etc/kairos/env ] || printf '# KAIROS_URL=http://<windows host>:8089   (found automatically when unset)\n' > /etc/kairos/env
grep -q '^user_allow_other' /etc/fuse.conf 2>/dev/null || echo user_allow_other >> /etc/fuse.conf

cat > /etc/wsl.conf <<'CONF'
[boot]
systemd=true

[user]
default=kairos

[network]
hostname=kairos-os
generateHosts=true

[interop]
appendWindowsPath=false
CONF
grep -q "kairos-os" /etc/hosts || echo "127.0.1.1 kairos-os" >> /etc/hosts

# The desktop user's systemd manager runs from boot, so WSL finds it at the first login.
mkdir -p /var/lib/systemd/linger && touch /var/lib/systemd/linger/kairos
# A lean OS: nothing here uses snaps.
systemctl disable snapd.service snapd.socket snapd.seeded.service >/dev/null 2>&1 || true
systemctl enable kairos-orgfs.service >/dev/null 2>&1 \
  || ln -sf /etc/systemd/system/kairos-orgfs.service /etc/systemd/system/multi-user.target.wants/kairos-orgfs.service
echo "kairos-os provisioned"
