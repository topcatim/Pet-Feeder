# Pet Feeder — Pi Zero Rebuild Guide

## ⚠️ Critical: OS Version

The feeder is an **original Pi Zero W** (ARMv6, one core). It runs **Raspberry Pi OS Lite 32-bit, Trixie (13)**, and the camera setup in `setup.sh` (picamera2 + `feeder-camrec`) is written for that.

Always use the **32-bit Lite** image. The 64-bit images don't run on a Pi Zero v1, and the Desktop version wastes RAM the Pi Zero doesn't have to spare.

---

## Step 1 — Flash the SD Card

1. Download **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. In the imager:
   - **Device**: Raspberry Pi Zero
   - **OS**: Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)** — confirm it says *Trixie*
   - **Storage**: your SD card (8GB minimum, 16GB recommended for video storage)

3. Click the **⚙️ gear icon** (OS Customisation) before writing:

   | Setting | Value |
   |---------|-------|
   | Hostname | `petfeeder` |
   | Enable SSH | ✅ Password authentication |
   | Username | `pi` |
   | Password | (something strong) |
   | WiFi SSID | your network name |
   | WiFi password | your WiFi password |
   | WiFi country | `GB` |
   | Locale | `Europe/London` |
   | Keyboard | `gb` |

4. Write the card, insert into Pi Zero, power on.

---

## Step 2 — Connect via SSH

The Pi Zero may take **3–5 minutes** on first boot (it's slow — be patient).

```bash
ssh pi@192.168.1.210
# or try:
ssh pi@petfeeder.local
```

---

## Step 3 — Run the Setup Script

One command does everything:

```bash
curl -O https://raw.githubusercontent.com/topcatim/Pet-Feeder/main/setup.sh
sudo bash setup.sh
```

**This takes 15–25 minutes on a Pi Zero.** It will:
- Update the OS
- Enable camera, I2C, serial interfaces
- Install Apache, mod_wsgi, picamera2, PyAV, sqlite3
- Create a Python virtualenv with all dependencies
- Clone the app from GitHub
- Configure Apache, the camera service (feeder-camrec), log rotation
- Install systemd services for button listener and feed scheduler
- Apply security hardening (fail2ban, UFW firewall, SSH key-only auth)

---

## Step 4 — Add Google API Credentials (optional)

The feeder can also log feed times to Google Sheets. Everything else works without it (the
current Pi has no credentials file), and the Google libraries are only loaded when a sheet
update actually runs. To turn it on you need a service account credentials file:

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Select your project → APIs & Services → Credentials
3. Download the service account JSON key
4. Copy it to the Pi:

```bash
scp googleapisecret.json pi@192.168.1.210:/var/www/feeder/feeder/googleapisecret.json
```

5. Make sure the spreadsheet `PetFeederTimes` is shared with the service account email address.

---

## Step 5 — Add Your SSH Public Key

Before the script disables password auth, add your key:

```bash
ssh-copy-id pi@192.168.1.210
```

Or manually paste your public key into `/home/pi/.ssh/authorized_keys`.

---

## Step 6 — Start Services and Reboot

```bash
sudo reboot
```

After reboot (give it 60 seconds):

```bash
# Check everything is running
sudo systemctl status apache2
sudo systemctl status feeder-camrec
sudo systemctl status feederbutton
sudo systemctl status feedertimer

# Watch logs
tail -f /var/www/feeder/feeder/logs/apacheError.log
```

---

## Step 7 — Access the Web UI

The web UI is only reachable over **Tailscale HTTPS** — Apache listens on `127.0.0.1:80`
and Tailscale serve publishes it to your tailnet (tailnet only, no Funnel). Plain
`http://<pi-ip>` on the LAN is refused by design.

If the setup script couldn't do it (Tailscale wasn't logged in yet):
```bash
sudo tailscale up
sudo tailscale serve --bg --https=443 http://127.0.0.1:80
sudo tailscale serve status        # shows the address
```
HTTPS certificates must be enabled for the tailnet (admin console → DNS → HTTPS
Certificates). Then open, from any device on your tailnet:
```
https://cat-feeder.tailb8be4c.ts.net
```

Default login is set during `createFiles.py` — check the upstream docs if you've forgotten it, or reset the database.

---

## Step 8 — Let the Admin Page Control Services

The admin page shows the status of the button, scheduler, camera and SSH services (read with
one `systemctl show` call, no sudo needed). Its **start/stop** buttons run `sudo service …`
as the app's user, which needs a sudo rule. `setup.sh` doesn't create it yet; on the current
Pi it is `/etc/sudoers.d/020_feeder-web`:

```bash
sudo tee /etc/sudoers.d/020_feeder-web.tmp >/dev/null <<'EOF'
feeder ALL=(root) NOPASSWD: /usr/sbin/service feeder-camrec start, /usr/sbin/service feeder-camrec stop, /usr/sbin/service feederButtonService start, /usr/sbin/service feederButtonService stop, /usr/sbin/service feederButtonService status, /usr/sbin/service feederTimeService start, /usr/sbin/service feederTimeService stop, /usr/sbin/service feederTimeService status
EOF
sudo visudo -cf /etc/sudoers.d/020_feeder-web.tmp && sudo mv /etc/sudoers.d/020_feeder-web.tmp /etc/sudoers.d/020_feeder-web
```
Replace `feeder` with the user the app runs as (the `WSGIDaemonProcess user=` in the Apache
config) and the service names with yours. SSH has no start/stop rule on purpose: stopping it
from a web page could lock you out.

---

## How the Web UI Is Served

```
iPhone ──HTTPS (tailnet only)──▶ tailscaled :443 ──▶ Apache 127.0.0.1:80
                                                       ├─ /static/css, js, images → files, cached 1 week
                                                       └─ everything else → Flask app (mod_wsgi daemon, login)
                                                            └─ /live/stream ◀── feeder-camrec 127.0.0.1:8081
```

Kept this way because the Pi Zero has one slow core:

- **The app is loaded when Apache starts**, not on the first visit
  (`WSGIScriptAlias … process-group=feeder application-group=%{GLOBAL}`). Importing it takes
  about 8 s at boot and after Apache's nightly reload at 00:30 (log rotation); before, the
  first visitor waited 25–35 s.
- **Styling comes straight from Apache** with `Cache-Control: public, max-age=604800`, so
  moving between pages doesn't re-fetch ~10 files through Flask. Apache's `www-data` user has
  read ACLs on `static/css`, `static/js` and `static/images` only. After changing a CSS file,
  phones may show the old styling for up to a week unless reloaded.
- **Videos are not aliased**: `/static/video/…` goes through Flask so the login protects it.
- **`feedtimes(feeddate)` is indexed** (`createFiles.py` creates it). The newest-first feed
  lists took 0.24 s without it. On a database made before the index existed:
  ```bash
  sudo -u feeder sqlite3 /var/www/feeder/feeder/feeder.db "create index if not exists feedtimes_date on feedtimes(feeddate);"
  ```
- Typical page times on the Pi: home ~0.5 s, admin ~0.7 s, history ~0.35 s. A new browser
  connection spends about 1 s on the TLS handshake (done by tailscaled); later requests reuse it.

---

## Hardware Reference

### GPIO Pins (BOARD numbering)

| Component | Pin | Notes |
|-----------|-----|-------|
| Feed button | 3 | Pull-up, active LOW |
| Main hopper motor | 11 | Relay |
| Treat hopper motor | 18 | Relay |

### Camera
- Pi Camera v1 (ov5647 sensor, CSI ribbon connector), loaded with `dtoverlay=ov5647` in `config.txt`
- `feeder-camrec.service` runs `camera/camrecord.py`, which does everything camera-related:
  - records at **15 fps** with the Pi Zero's **hardware H.264 encoder** (about 40% of the one
    CPU core; the old motion setup maxed it out at 15 fps in software)
  - checks a tiny 80x60 copy of the image 5 times a second for movement, and saves
    `cam-YYYYMMDDHHMMSS.mp4` from 3 s before the movement to about 10 s after it (60 s max per file)
  - serves the live view (MJPEG, 3 fps) on `127.0.0.1:8081`; the web app shows it at `/live`
    behind the login
- Sensitivity and timings are constants at the top of `camrecord.py`
- It runs as the `motion` user (left over from the old motion setup, which it replaced)
- Recordings saved to `/var/www/feeder/feeder/static/video/`
- Videos auto-deleted after 1 day (configurable in `app.cfg`)

---

## Configuration Reference (`app.cfg`)

The setup script creates this automatically, but key values to know:

| Setting | Default | Description |
|---------|---------|-------------|
| `Feed_Button_GPIO_Pin` | 3 | Physical button GPIO (BOARD) |
| `Hopper_GPIO_Pin` | 11 | Main feed motor relay GPIO |
| `TreatHopper_GPIO_Pin` | 18 | Treat motor relay GPIO |
| `Hopper_Spin_Time` | 2.8 | Seconds motor runs per feed |
| `TreatHopper_Spin_Time` | 0.8 | Seconds treat motor runs |
| `Seconds_Delay_After_Button_Push` | 3 | Min gap between button presses |
| `Seconds_Delay_Between_Schedule_Checks` | 300 | How often scheduler checks feed times |
| `Number_Days_Of_Videos_To_Keep` | 1 | Auto-delete videos older than N days |
| `Camera_Address` | `http://192.168.1.210:8081` | Camera stream URL shown in UI |

---

## Remote Access

The Pi is accessible via **Tailscale** (already installed if Tailscale is on your account).

```bash
ssh pi@<tailscale-ip>
```

The web UI is at `https://cat-feeder.tailb8be4c.ts.net` from any device on the tailnet. No port
forwarding or DuckDNS required. To limit which tailnet devices can open it, use Tailscale's
access rules in the admin console.

---

## Troubleshooting

### Web UI not loading
```bash
sudo systemctl status apache2
tail -20 /var/www/feeder/feeder/logs/apacheError.log
sudo tailscale serve status        # should show / proxy http://127.0.0.1:80 (tailnet only)
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1/   # 302 = app answering
```

### Web UI slow
- First visit very slow (~30 s): the app isn't being preloaded — check the `WSGIScriptAlias`
  line still has `process-group=feeder application-group=%{GLOBAL}`.
- Every page slow and styling requests show in `feeder-access.log`: check
  `curl -sI http://127.0.0.1/static/css/navBar.css | grep -i cache-control` says `max-age=604800`.
- Admin start/stop buttons do nothing: check the sudo rule (Step 8) with `sudo -l -U feeder`.

### Camera not working / no recordings
The ribbon is marginal and the sensor sometimes fails to probe at boot. `feeder-camrec` re-probes
it up to 10 times before starting (`camera/probe-camera.sh`). Its log shows each movement and saved file.
```bash
systemctl status feeder-camrec
journalctl -u feeder-camrec -n 30
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8081/ --max-time 3   # live view (200 = OK)
sudo systemctl restart feeder-camrec
```
The web page hides the live view and videos when `feeder-camrec` isn't running.

### Feed button not working
```bash
sudo systemctl status feederbutton
tail -20 /var/www/feeder/feeder/logs/feederButtonService.log
```

### Scheduled feeds not triggering
```bash
sudo systemctl status feedertimer
tail -20 /var/www/feeder/feeder/logs/feederTimeService.log
```

### Google Sheets not updating
- Check `googleapisecret.json` exists at `/var/www/feeder/feeder/googleapisecret.json`
- Check the spreadsheet is shared with the service account email
- Check the spreadsheet name in `app.cfg` matches exactly

### High CPU / load average
The button service previously had a CPU spin bug (no sleep in its loop). This is fixed in the current codebase. If load is high:
```bash
ps aux --sort=-%cpu | head -10
```

---

## Security Notes

- SSH password authentication is **disabled** by setup script — key auth only
- fail2ban bans after **3 failed attempts** for **24 hours**
- UFW firewall: only port 22 (SSH) open. The web UI has no open port: Apache listens on
  `127.0.0.1:80` only and is reached through Tailscale serve (HTTPS, tailnet only)
- Local network (192.168.1.x) and Tailscale (100.x.x.x) are whitelisted in fail2ban
- Every page needs the app login, recorded videos included; only the login page and the
  styling files (CSS, JS, images) are public — and only to the tailnet
- The app's sudo rights are limited to starting/stopping the feeder services (Step 8)
- `app.cfg` is gitignored — never commit it (contains secret key)
- Google API credentials (`googleapisecret.json`) are gitignored — never commit
