#!/bin/bash

# Mady Bot (Heather) - Server Setup Script
# Tested on Ubuntu 20.04/22.04 and Debian 11/12

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Mady Bot (Heather) - Server Setup    ${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# Configuration
BOT_USER="madybot"
BOT_DIR="/opt/madybot"
SERVICE_NAME="madybot"

# Get environment variables from user
echo ""
echo -e "${YELLOW}Enter your configuration:${NC}"
read -p "Telegram Bot Token: " BOT_TOKEN
read -p "Blackbox API Key (press Enter to skip): " BLACKBOX_API_KEY
read -p "PostgreSQL Database URL (press Enter for SQLite): " DATABASE_URL
read -p "HTTP Proxy URL (press Enter to skip): " PROXY_HTTP
echo ""
echo -e "${YELLOW}Stripe Keys (optional - needed for Stripe gateways):${NC}"
read -p "Stripe Secret Key (sk_live_...): " STRIPE_SECRET_KEY
read -p "Stripe Public Key (pk_live_...): " STRIPE_PUBLIC_PK

# Validate required fields
if [ -z "$BOT_TOKEN" ]; then
    echo -e "${RED}Bot token is required!${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}[1/7] Installing system dependencies...${NC}"
apt-get update
apt-get install -y python3 python3-pip python3-venv git curl

echo ""
echo -e "${GREEN}[2/7] Creating bot user and directory...${NC}"
# Create user if doesn't exist
if ! id "$BOT_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$BOT_DIR" "$BOT_USER"
fi

# Create directory structure
mkdir -p "$BOT_DIR"
mkdir -p "$BOT_DIR/logs"

echo ""
echo -e "${GREEN}[3/7] Copying bot files...${NC}"
# Copy files from current directory (assumes script is run from SRCAndMore/deploy)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR/../"* "$BOT_DIR/" 2>/dev/null || {
    echo -e "${YELLOW}Note: Run this script from the deploy directory, or copy files manually to $BOT_DIR${NC}"
}

echo ""
echo -e "${GREEN}[4/7] Setting up Python virtual environment...${NC}"
cd "$BOT_DIR"
python3 -m venv venv
source venv/bin/activate

# Install requirements
if [ -f "requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
else
    pip install --upgrade pip
    pip install python-telegram-bot>=20.0 requests httpx aiohttp SQLAlchemy psycopg2-binary faker beautifulsoup4
fi

deactivate

echo ""
echo -e "${GREEN}[5/7] Creating environment file...${NC}"
cat > "$BOT_DIR/.env" << EOF
BOT_TOKEN=$BOT_TOKEN
BLACKBOX_API_KEY=$BLACKBOX_API_KEY
DATABASE_URL=$DATABASE_URL
PROXY_HTTP=$PROXY_HTTP
PROXY_HTTPS=$PROXY_HTTP
STRIPE_SECRET_KEY=$STRIPE_SECRET_KEY
STRIPE_PUBLIC_PK=$STRIPE_PUBLIC_PK
STRIPE_FALLBACK_PK=$STRIPE_PUBLIC_PK
EOF

echo ""
echo -e "${GREEN}[6/7] Setting permissions...${NC}"
chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR"
chmod 600 "$BOT_DIR/.env"
chmod +x "$BOT_DIR/transferto.py" 2>/dev/null || true

echo ""
echo -e "${GREEN}[7/7] Creating systemd service...${NC}"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Mady Bot (Heather)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$BOT_USER
Group=$BOT_USER
WorkingDirectory=$BOT_DIR
Environment=PATH=$BOT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=$BOT_DIR/.env
ExecStart=$BOT_DIR/venv/bin/python3 $BOT_DIR/transferto.py

# Auto-healing: restart on failure
Restart=always
RestartSec=10

# Stop gracefully
TimeoutStopSec=30
KillMode=mixed

# Resource limits
MemoryMax=512M
CPUQuota=80%

# Logging
StandardOutput=append:$BOT_DIR/logs/bot.log
StandardError=append:$BOT_DIR/logs/bot_error.log

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation Complete!               ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Bot installed to: ${YELLOW}$BOT_DIR${NC}"
echo -e "Service name: ${YELLOW}$SERVICE_NAME${NC}"
echo ""
echo -e "${YELLOW}Commands:${NC}"
echo -e "  Start bot:    ${GREEN}sudo systemctl start $SERVICE_NAME${NC}"
echo -e "  Stop bot:     ${GREEN}sudo systemctl stop $SERVICE_NAME${NC}"
echo -e "  Restart bot:  ${GREEN}sudo systemctl restart $SERVICE_NAME${NC}"
echo -e "  View status:  ${GREEN}sudo systemctl status $SERVICE_NAME${NC}"
echo -e "  View logs:    ${GREEN}sudo journalctl -u $SERVICE_NAME -f${NC}"
echo -e "  View bot log: ${GREEN}tail -f $BOT_DIR/logs/bot.log${NC}"
echo ""
echo -e "${YELLOW}Start the bot now? (y/n)${NC}"
read -p "" START_NOW

if [ "$START_NOW" = "y" ] || [ "$START_NOW" = "Y" ]; then
    systemctl start "$SERVICE_NAME"
    sleep 2
    systemctl status "$SERVICE_NAME" --no-pager
fi

echo ""
echo -e "${GREEN}Done! Your bot will auto-restart if it crashes.${NC}"
