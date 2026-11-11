#!/bin/bash
# =============================================================================
# Pet Feeder — Raspberry Pi Zero (original) Setup Script
# =============================================================================
# Target OS: Raspberry Pi OS Bullseye Lite 32-bit (REQUIRED for Pi Zero v1)
#            Do NOT use Bookworm — it dropped ARMv6 support.
#
# Usage: sudo bash setup.sh
#
# What this does:
#   1. System update
#   2. Enable camera, I2C, serial interfaces
#   3. Install system dependencies (Apache, mod_wsgi, motion, sqlite3)
#   4. Create Python virtualenv and install pip packages
#   5. Clone pet feeder app from GitHub
#   6. Configure Apache virtual host
#   7. Configure motion (camera)
#   8. Install init.d services (button + time scheduler)
#   9. Set up log rotation
#  10. Set correct permissions
# =============================================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()  { echo -e "\n${CYAN}>>> $1${NC}"; }

[[ $EUID -ne 0 ]] && error "Run as root: sudo bash setup.sh"

# =============================================================================
# CONFIGURATION — edit these before running
# =============================================================================
FEEDER_USER="pi"
APP_DIR="/var/www/feeder"
REPO_URL="https://github.com/topcatim/Pet-Feeder.git"

# GPIO pins (BOARD numbering)
FEED_BUTTON_PIN=3
HOPPER_PIN=11
TREAT_HOPPER_PIN=18

# Hopper run times (seconds)
HOPPER_TIME=2.8
TREAT_HOPPER_TIME=0.8

# Google Sheets spreadsheet name (must match your Sheet exactly)
SPREADSHEET_NAME="PetFeederTimes"

# Video storage — how many days to keep
DAYS_VIDEOS_TO_KEEP=1

# Camera stream — update if you expose this externally
CAMERA_ADDRESS="http://192.168.1.210:8081"

# Flask secret key — change this to something random
SECRET_KEY="$(openssl rand -hex 24)"


# =============================================================================
# 1. SYSTEM UPDATE
# =============================================================================
step "Updating system packages"
apt-get update -qq
apt-get upgrade -y -qq
info "System updated"

# =============================================================================
# 2. ENABLE INTERFACES
# =============================================================================
step "Enabling interfaces"

info "Enabling camera..."
raspi-config nonint do_camera 0

info "Enabling I2C..."
raspi-config nonint do_i2c 0

info "Enabling serial hardware (no login shell)..."
raspi-config nonint do_serial_hw 0
raspi-config nonint do_serial_cons 1

# Load camera module at boot
if ! grep -q "bcm2835-v4l2" /etc/modules; then
    echo "bcm2835-v4l2" >> /etc/modules
    info "Added bcm2835-v4l2 to /etc/modules"
fi

# =============================================================================
# 3. SYSTEM DEPENDENCIES
# =============================================================================
step "Installing system packages"
apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    apache2 \
    apache2-dev \
    libapache2-mod-wsgi-py3 \
    sqlite3 \
    motion \
    git \
    logrotate \
    usbutils \
    i2c-tools

info "System packages installed"

# =============================================================================
# 4. PYTHON VIRTUALENV & PACKAGES
# =============================================================================
step "Setting up Python virtualenv"

mkdir -p "$APP_DIR"
python3 -m venv "$APP_DIR/venv"
chown -R ${FEEDER_USER}:www-data "$APP_DIR"

info "Installing Python packages into virtualenv..."
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet \
    flask \
    markupsafe \
    RPi.GPIO \
    gspread \
    gspread-formatting \
    oauth2client \
    Adafruit-CharLCD

info "Python packages installed"

# =============================================================================
# 5. CLONE APP FROM GITHUB
# =============================================================================
step "Cloning Pet Feeder app"

if [[ -d "$APP_DIR/feeder" ]]; then
    warn "$APP_DIR/feeder already exists — pulling latest..."
    cd "$APP_DIR/feeder" && sudo -u ${FEEDER_USER} git pull
else
    sudo -u ${FEEDER_USER} git clone "$REPO_URL" "$APP_DIR/feeder"
fi

# Create required directories
mkdir -p "$APP_DIR/feeder/logs"
mkdir -p "$APP_DIR/feeder/static/video"

# Create database
if [[ ! -f "$APP_DIR/feeder/feeder.db" ]]; then
    info "Creating SQLite database..."
    cd "$APP_DIR/feeder" && "$APP_DIR/venv/bin/python" createFiles.py
fi

# Write config file
info "Writing app.cfg..."
cat > "$APP_DIR/feeder/app.cfg" << EOF
[feederConfig]
Database_Location=$APP_DIR/feeder/feeder.db
Feed_Button_GPIO_Pin=$FEED_BUTTON_PIN
Hopper_GPIO_Pin=$HOPPER_PIN
TreatHopper_GPIO_Pin=$TREAT_HOPPER_PIN
Hopper_Spin_Time=$HOPPER_TIME
TreatHopper_Spin_Time=$TREAT_HOPPER_TIME
Log_ButtonService_Filename=$APP_DIR/feeder/logs/feederButtonService.log
Log_TimeService_Filename=$APP_DIR/feeder/logs/feederTimeService.log
Motion_Video_Dir_Path=$APP_DIR/feeder/static/video
Motion_Camera_Site_Address=$CAMERA_ADDRESS
Number_Days_Of_Videos_To_Keep=$DAYS_VIDEOS_TO_KEEP
Number_Feed_Times_To_Display=5
Number_Scheduled_Feed_Times_To_Display=5
Number_Videos_To_Display=100
Seconds_Delay_After_Button_Push=3
Seconds_Delay_Between_Schedule_Checks=300
Secretkey=$SECRET_KEY
Spreadsheet_File_Name=$SPREADSHEET_NAME
EOF

warn "app.cfg written. You will need to add your Google API credentials"
warn "file to: $APP_DIR/feeder/googleapisecret.json"

# =============================================================================
# 6. APACHE CONFIGURATION
# =============================================================================
step "Configuring Apache"

# Update feeder.wsgi to use virtualenv
cat > "$APP_DIR/feeder/feeder.wsgi" << EOF
import sys
activate_this = '$APP_DIR/venv/bin/activate_this.py'
exec(compile(open(activate_this, "rb").read(), activate_this, 'exec'))
sys.path.append('$APP_DIR/feeder')
from app import app as application
EOF

# Write Apache vhost
cat > /etc/apache2/sites-available/000-default.conf << EOF
<VirtualHost *:80>
    WSGIDaemonProcess feeder user=www-data group=www-data threads=3
    WSGIScriptAlias / $APP_DIR/feeder/feeder.wsgi

    <Directory $APP_DIR/feeder>
        WSGIProcessGroup feeder
        Require all granted
    </Directory>

    <Files feeder.wsgi>
        Require all granted
    </Files>

    ErrorLog $APP_DIR/feeder/logs/apacheError.log
    CustomLog $APP_DIR/feeder/logs/apacheAccess.log combined
</VirtualHost>
EOF

a2enmod headers wsgi 2>/dev/null || true

# Add www-data to gpio and video groups for GPIO + camera access
usermod -aG gpio www-data
usermod -aG video www-data

info "Apache configured"

# =============================================================================
# 7. MOTION (camera)
# =============================================================================
step "Configuring motion"

# Add pi user to motion group
usermod -aG motion ${FEEDER_USER}

cat > /etc/motion/motion.conf << EOF
daemon off
setup_mode off
log_level 6
target_dir $APP_DIR/feeder/static/video
videodevice /dev/video0
width 640
height 480
framerate 15
text_left CAMERA1
text_right %Y-%m-%d\n%T-%q
emulate_motion off
threshold 1500
despeckle_filter EedDl
minimum_motion_frames 1
event_gap 60
pre_capture 3
post_capture 0
picture_output off
picture_filename %Y%m%d%H%M%S-%q
movie_output on
movie_max_time 60
movie_quality 45
movie_codec mp4
movie_filename %t-%v-%Y%m%d%H%M%S
webcontrol_port 8080
webcontrol_localhost on
webcontrol_parms 0
stream_port 8081
# The stream only listens on the Pi; the web app shows it at /live behind its login
stream_localhost on
EOF

# Motion camera startup delay (prevents race condition with bcm2835 driver)
mkdir -p /etc/systemd/system/motion.service.d
cat > /etc/systemd/system/motion.service.d/camera-wait.conf << EOF
[Service]
ExecStartPre=/bin/sleep 15
EOF

info "Motion configured with 15s startup delay (prevents camera busy errors)"

# =============================================================================
# 8. SERVICES (button listener + feed scheduler)
# =============================================================================
step "Installing feeder services"

# feederButtonService
cat > /etc/systemd/system/feederbutton.service << EOF
[Unit]
Description=Pet Feeder Button Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR/feeder
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/feeder/feederButtonService.py
Restart=on-failure
RestartSec=10
StandardOutput=append:$APP_DIR/feeder/logs/feederButtonService.log
StandardError=append:$APP_DIR/feeder/logs/feederButtonService.log

[Install]
WantedBy=multi-user.target
EOF

# feederTimeService
cat > /etc/systemd/system/feedertimer.service << EOF
[Unit]
Description=Pet Feeder Time Schedule Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR/feeder
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/feeder/feederTimeService.py
Restart=on-failure
RestartSec=10
StandardOutput=append:$APP_DIR/feeder/logs/feederTimeService.log
StandardError=append:$APP_DIR/feeder/logs/feederTimeService.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable feederbutton.service feedertimer.service
info "feederbutton and feedertimer services enabled"

# =============================================================================
# 9. LOG ROTATION
# =============================================================================
step "Setting up log rotation"

cat > /etc/logrotate.d/petfeeder << EOF
$APP_DIR/feeder/logs/*.log {
    daily
    rotate 3
    compress
    missingok
    notifempty
}
EOF

info "Log rotation configured (3 days)"

# =============================================================================
# 10. PERMISSIONS
# =============================================================================
step "Setting permissions"

chown -R ${FEEDER_USER}:www-data "$APP_DIR"
chmod -R 750 "$APP_DIR"
chmod -R 770 "$APP_DIR/feeder"
chmod 640 "$APP_DIR/feeder/app.cfg"

info "Permissions set"

# =============================================================================
# SECURITY HARDENING
# =============================================================================
step "Applying security hardening"

# fail2ban
apt-get install -y -qq fail2ban

cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime  = 86400
findtime = 600
maxretry = 3
ignoreip = 127.0.0.1/8 192.168.1.0/24 100.0.0.0/8

[sshd]
enabled  = true
port     = ssh
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 3
bantime  = 86400
EOF

# UFW
apt-get install -y -qq ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP feeder'
ufw --force enable

# Disable password auth (key auth only)
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config

systemctl enable fail2ban
systemctl restart fail2ban ssh

info "Firewall, fail2ban, SSH key-only auth configured"

# =============================================================================
# DONE
# =============================================================================
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Pet Feeder setup complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Add your Google API credentials:"
echo "     Copy googleapisecret.json to $APP_DIR/feeder/googleapisecret.json"
echo ""
echo "  2. Install your SSH public key:"
echo "     ssh-copy-id pi@$(hostname -I | awk '{print $1}')"
echo ""
echo "  3. Start services:"
echo "     sudo systemctl start apache2 motion feederbutton feedertimer"
echo ""
echo "  4. Check logs:"
echo "     tail -f $APP_DIR/feeder/logs/apacheError.log"
echo ""
echo "  Web UI login: every page needs a login. Change the default admin password (ChangeMe!) straight away."
echo ""
echo "  5. Access feeder web UI:"
echo "     http://$(hostname -I | awk '{print $1}')"
echo ""
warn "Reboot recommended to activate camera and interface changes:"
echo "     sudo reboot"
