#!/bin/bash
# netwatch: gets a Raspberry Pi back on Wi-Fi after the router restarts.
#
# On 28 Nov 2026 an eero firmware update restarted Tim's router at about 02:05; the cat flap Pi
# never rejoined and was offline for six hours. Every Pi gets this (installed by install-netwatch.sh;
# the original is ai-cat-flap pi/netwatch.sh). Every 30 s it pings the router. If it can't be reached:
#   after 3 min: Wi-Fi off and on again
#   after 6 min: restart NetworkManager
#   after 10 min: reboot (at most once an hour, so a long router outage doesn't reboot-loop;
#                 after that, Wi-Fi off and on every 3 min)
# Its log: journalctl -u <name>-netwatch
#
# Test without touching anything:
#   NETWATCH_GW=<unused IP> NETWATCH_DRY_RUN=1 NETWATCH_SCALE=30 NETWATCH_STAMP=/tmp/nw ./netwatch.sh
CHECK=30 RESET_WIFI=180 RESET_NM=360 REBOOT=600 REBOOT_GAP=3600
SCALE=${NETWATCH_SCALE:-1}   # divide every time by this (tests only)
STAMP=${NETWATCH_STAMP:-/var/lib/netwatch/last-reboot}

log() { echo "netwatch: $*"; }
act() { log "$1"; [[ -n "$NETWATCH_DRY_RUN" ]] && return; shift; "$@"; }
uptime_s() { local up; read -r up _ < /proc/uptime; echo "${up%.*}"; }

wifi_cycle() { act "$1: Wi-Fi off and on" sh -c 'nmcli radio wifi off; sleep 5; nmcli radio wifi on'; }

down_since=; step=0; last_nudge=0
while true; do
  gw=${NETWATCH_GW:-$(ip -4 route show default | awk '{print $3; exit}')}
  gw=${gw:-192.168.4.1}   # no default route at all: the home router
  if ping -c2 -W3 "$gw" >/dev/null 2>&1; then
    [[ -n $down_since ]] && log "router $gw reachable again after $(( ($(uptime_s) - down_since) * SCALE )) s"
    down_since=; step=0
  else
    now=$(uptime_s)
    [[ -z $down_since ]] && { down_since=$now; log "router $gw not answering"; }
    down=$(( (now - down_since) * SCALE ))
    if (( down >= REBOOT )); then
      wall=$(date +%s); last=$(cat $STAMP 2>/dev/null || echo 0)
      # the wall clock can jump on a Pi with no battery clock: a stamp in the future doesn't block a reboot
      if (( wall - last >= REBOOT_GAP / SCALE || wall < last )); then
        [[ -z "$NETWATCH_DRY_RUN" ]] && { mkdir -p "${STAMP%/*}"; echo "$wall" > $STAMP; }
        act "no router for $down s: rebooting" systemctl reboot
        [[ -n "$NETWATCH_DRY_RUN" ]] && exit 0
        sleep 120   # reboot under way
      elif (( (now - last_nudge) * SCALE >= RESET_WIFI )); then
        wifi_cycle "no router for $down s, rebooted less than an hour ago"; last_nudge=$now
      fi
    elif (( down >= RESET_NM && step < 2 )); then
      act "no router for $down s: restarting NetworkManager" systemctl restart NetworkManager; step=2; last_nudge=$now
    elif (( down >= RESET_WIFI && step < 1 )); then
      wifi_cycle "no router for $down s"; step=1; last_nudge=$now
    fi
  fi
  sleep $(( CHECK / SCALE ))
done
