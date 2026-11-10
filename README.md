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
- **The camera stream (port 8081) needs a login** (`motion` basic auth, user `feeder`); the password is in `/etc/motion/motion.conf` (root:motion, 640).
- Change the default `admin` password (`ChangeMe!`) on any new install.
