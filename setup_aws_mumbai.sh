#!/bin/bash
# ==============================================================================
# AWS Mumbai (ap-south-1) - One-Click 24/7 Setup Script for Rooter PSN Bots
# Supports Ubuntu 22.04 LTS & Ubuntu 24.04 LTS
# ==============================================================================
set -e

echo "=========================================================="
echo "🚀 Setting up PlayStation Restock & Buy Bots on AWS Mumbai"
echo "=========================================================="

# 1. Update system & install core tools
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git curl wget

BASE_DIR="/home/ubuntu/rooter_bots"
mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

# 2. Clone or update Stock_Notify_Bot (Bot 1)
if [ ! -d "Stock_Notify_Bot" ]; then
    echo "📥 Cloning Stock_Notify_Bot..."
    git clone https://github.com/aakash07l/Stock_Notify_Bot.git
else
    echo "🔄 Updating Stock_Notify_Bot..."
    cd Stock_Notify_Bot && git pull origin main && cd ..
fi

# 3. Clone or update psn-buy-bot (Bot 2)
if [ ! -d "psn-buy-bot" ]; then
    echo "📥 Cloning psn-buy-bot..."
    git clone https://github.com/aakash07l/psn-buy-bot.git
else
    echo "🔄 Updating psn-buy-bot..."
    cd psn-buy-bot && git pull origin main && cd ..
fi

# 4. Setup Python Virtual Environment for Stock_Notify_Bot (Bot 1)
echo "🐍 Setting up Python environment for Bot 1 (Stock Monitor)..."
cd "$BASE_DIR/Stock_Notify_Bot"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install --with-deps chromium || playwright install chromium
if [ ! -f ".env" ]; then
    cp .env.example .env
fi
deactivate

# 5. Setup Python Virtual Environment for psn-buy-bot (Bot 2)
echo "🐍 Setting up Python environment for Bot 2 (Buy Sniper)..."
cd "$BASE_DIR/psn-buy-bot"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install --with-deps chromium || playwright install chromium
if [ ! -f ".env" ]; then
    cp .env.example .env
fi
deactivate

# 6. Install Systemd 24/7 Auto-Restart Services
echo "⚙️ Creating 24/7 background systemd services..."

# Service 1: Stock Monitor
sudo bash -c "cat <<EOF > /etc/systemd/system/stock-monitor.service
[Unit]
Description=PlayStation Stock Monitor Bot (Bot 1)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$BASE_DIR/Stock_Notify_Bot
ExecStart=$BASE_DIR/Stock_Notify_Bot/venv/bin/python main.py
Restart=always
RestartSec=3s
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF"

# Service 2: Buy Sniper
sudo bash -c "cat <<EOF > /etc/systemd/system/buy-bot.service
[Unit]
Description=PlayStation Sniper Buy Bot (Bot 2)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$BASE_DIR/psn-buy-bot
ExecStart=$BASE_DIR/psn-buy-bot/venv/bin/python main.py
Restart=always
RestartSec=3s
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF"

# 7. Reload systemd and start both services
sudo systemctl daemon-reload
sudo systemctl enable stock-monitor
sudo systemctl enable buy-bot

sudo systemctl restart buy-bot
sudo systemctl restart stock-monitor

echo "=========================================================="
echo "✅ SETUP COMPLETE! Both bots are now running 24/7 on AWS!"
echo "=========================================================="
echo "Commands to check status:"
echo "  sudo systemctl status stock-monitor"
echo "  sudo systemctl status buy-bot"
echo "To view live logs:"
echo "  journalctl -u stock-monitor -f"
echo "  journalctl -u buy-bot -f"
echo "=========================================================="
