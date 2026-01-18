#!/bin/bash

# Mady Bot (Heather) - Uninstall Script

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SERVICE_NAME="madybot"
BOT_DIR="/opt/madybot"
BOT_USER="madybot"

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}This will completely remove Mady Bot (Heather) from your system.${NC}"
read -p "Are you sure? (y/n): " CONFIRM

if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Cancelled."
    exit 0
fi

echo -e "${GREEN}[1/4] Stopping service...${NC}"
systemctl stop "$SERVICE_NAME" 2>/dev/null || true
systemctl disable "$SERVICE_NAME" 2>/dev/null || true

echo -e "${GREEN}[2/4] Removing systemd service...${NC}"
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload

echo -e "${GREEN}[3/4] Removing bot files...${NC}"
rm -rf "$BOT_DIR"

echo -e "${GREEN}[4/4] Removing bot user...${NC}"
userdel "$BOT_USER" 2>/dev/null || true

echo ""
echo -e "${GREEN}Uninstall complete!${NC}"
