# Pet Feeder

Automated cat feeder based on [DiyPetFeeder](https://gitlab.com/DiyPetFeeder/feeder) running on Raspberry Pi.

## Hardware
- Raspberry Pi Zero W (original, one ARMv6 core) on Raspberry Pi OS Lite 32-bit, Trixie
- GPIO-controlled hopper motors (food and treats)
- Physical feed button
- LCD screen
- Pi Camera v1: records movement as H.264 `.mp4` (plays on iPhone) and shows a live view
- Optional Google Sheets logging

## Setup
See [REBUILD.md](REBUILD.md) — flash the card, run `setup.sh`, then the few manual steps.

## Web UI
- Flask app under Apache/mod_wsgi, reachable **only over Tailscale HTTPS**
  (`https://cat-feeder.tailb8be4c.ts.net`, tailnet only). Apache itself only listens on `127.0.0.1`.
- Tuned for the Pi Zero: the app is preloaded when Apache starts, styling files are served by
  Apache and cached by the browser for a week. Details in REBUILD.md, *How the Web UI Is Served*.
- Admin page: status and start/stop for the button, scheduler and camera services.

## Security

- **Every page needs a login** (Flask session, 30 days), including the feed buttons and recorded videos. Only the login page and page styling are public (and only to the tailnet).
- **Live video** is at `/live`, behind the same login. The camera's live view (port 8081, from `camera/camrecord.py`) only listens on the Pi itself; the page fetches single frames through the app (~3 a second), which works in iPhone Safari.
- Change the default `admin` password (`ChangeMe!`) on any new install.
