#!/bin/bash
echo "[*] Stopping any existing bot instances..."
pkill -9 -f "python.*transferto.py" 2>/dev/null || true
sleep 5
echo "[*] Starting Telegram Bot..."
exec python transferto.py
