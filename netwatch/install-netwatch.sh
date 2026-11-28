#!/bin/bash
# Makes this Pi stay on Wi-Fi after a router restart (Tim's standing rule for every Pi, 28 Nov 2026):
#   1. Wi-Fi power saving off (NetworkManager setting, and right now)
#   2. the netwatch service (netwatch.sh, next to this script): Wi-Fi reset, then reboot
# Usage: sudo bash install-netwatch.sh <name>    e.g. hydro -> hydro-netwatch.service
# Safe to re-run. Keeping the journal across reboots is done by each project's own setup.
set -e
[[ $EUID -ne 0 ]] && { echo "run as root"; exit 1; }
NAME=${1:?usage: install-netwatch.sh <name>}
HERE="$(cd "$(dirname "$0")" && pwd)"
if [[ -d /etc/NetworkManager/conf.d ]]; then
  printf '[connection]\n# Wi-Fi power saving can stop a Pi reconnecting\nwifi.powersave = 2\n' \
    > /etc/NetworkManager/conf.d/$NAME-wifi-powersave.conf
  systemctl reload NetworkManager 2>/dev/null || true
else
  echo "warning: no NetworkManager; netwatch's resets use nmcli and will not work" >&2
fi
iw dev wlan0 set power_save off 2>/dev/null || true
install -m 755 "$HERE/netwatch.sh" /usr/local/sbin/$NAME-netwatch
cat > /etc/systemd/system/$NAME-netwatch.service << UNIT
[Unit]
Description=$NAME: get back on Wi-Fi after a router restart (Wi-Fi reset, then reboot)
After=network.target

[Service]
ExecStart=/usr/local/sbin/$NAME-netwatch
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable $NAME-netwatch.service >/dev/null
systemctl restart $NAME-netwatch.service
echo "Wi-Fi power saving off; $NAME-netwatch running (journalctl -u $NAME-netwatch)"
