#!/bin/bash

# Mady Bot (Heather) - Update Script
# Use this to update bot files without losing configuration

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

BOT_DIR="/opt/madybot"
SERVICE_NAME="madybot"

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (use sudo)"
    exit 1
fi

echo -e "${GREEN}Updating Mady Bot (Heather)...${NC}"

# Stop bot
echo "[1/4] Stopping bot..."
systemctl stop "$SERVICE_NAME"

# Backup .env
echo "[2/4] Backing up configuration..."
cp "$BOT_DIR/.env" /tmp/madybot_env_backup

# Copy new files (assumes you've uploaded them to /tmp/madybot_update)
echo "[3/4] Copying new files..."
if [ -d "/tmp/madybot_update" ]; then
    cp -r /tmp/madybot_update/* "$BOT_DIR/"
    rm -rf /tmp/madybot_update
else
    echo -e "${YELLOW}No update files found in /tmp/madybot_update${NC}"
    echo "Upload your updated bot files there first."
fi

# Restore .env
cp /tmp/madybot_env_backup "$BOT_DIR/.env"

# Fix permissions
chown -R madybot:madybot "$BOT_DIR"
chmod 600 "$BOT_DIR/.env"

# Update dependencies
echo "[4/4] Updating dependencies..."
source "$BOT_DIR/venv/bin/activate"
pip install -r "$BOT_DIR/requirements.txt" --quiet
deactivate

# Restart
systemctl start "$SERVICE_NAME"
sleep 2

echo ""
echo -e "${GREEN}Update complete!${NC}"
systemctl status "$SERVICE_NAME" --no-pager
