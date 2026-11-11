# Pet Feeder

Automated cat feeder based on [DiyPetFeeder](https://gitlab.com/DiyPetFeeder/feeder) running on Raspberry Pi.

## Hardware
- Raspberry Pi (original)
- GPIO-controlled hopper motor
- Physical feed button
- LCD screen
- Google Sheets logging

## Setup
See REBUILD.md (coming soon)

## Security

- **Every page needs a login** (Flask session, 30 days), including the feed buttons and recorded videos. Only the login page and page styling are public.
- **Live video** is at `/live`, behind the same login. `motion`'s stream (port 8081) only listens on the Pi itself (`stream_localhost on`).
- Change the default `admin` password (`ChangeMe!`) on any new install.
