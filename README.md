# 🎮 PlayStation Stock Monitor & Restock Trigger Bot (Bot 1)

24/7 unauthenticated restock monitor for **Rooter Shop PlayStation Gift Cards**.
Specifically tracks **₹1,000, ₹2,000, ₹3,000, ₹4,000, and ₹5,000** denominations.

## 🚀 Key Features
- **Zero Authentication / No Ban Risk:** Runs completely unauthenticated without account credentials. Rooter accounts will never get banned for checking stock.
- **Dual-Engine Sweeper:**
  - **Ultra-Fast HTTP Parser (Primary):** Checks Next.js embedded data in under 500ms using `httpx`. Consumes `< 15MB` RAM.
  - **Playwright Headless (Fallback):** Automatically kicks in if anti-bot challenges occur.
- **Instant Webhook to Buy Bot (< 2ms):** Dispatches an internal HTTP POST to `http://127.0.0.1:5000/webhook/stock` on localhost as soon as stock appears.
- **Telegram Notifications:** Sends HTML restock alerts to both configured Admin Telegram Chat IDs.
- **24/7 Reliability:** Auto-recovers from network glitches, includes keep-alive server on port `8080`.

---

## ⚙️ Configuration (`.env`)
```ini
TELEGRAM_BOT_TOKEN=8971931761:AAHZEBDz0QCq6WadUQa8Foiw4Gc0mtU_Css
TELEGRAM_CHAT_ID=5701727023,1988639571
BUY_BOT_WEBHOOK_URL=http://127.0.0.1:5000/webhook/stock
INTERNAL_SECRET=psn_sniper_secret_key_2026
TARGET_DENOMINATION=1000
TARGET_QUANTITY=2
CHECK_INTERVAL_SECONDS=3
ALERT_COOLDOWN_SECONDS=90
PORT=8080
```

---

## 🤖 Telegram Commands
- `/status` - View current stock across all denominations and bot uptime.
- `/check` - Run an immediate manual stock sweep.
- `/set_target <amount> [quantity]` - Update target voucher denomination and quantity (e.g. `/set_target 1000 2`).
- `/test_trigger` - Send a dry-run restock signal to Buy Bot.

---

## 🏃 Run Locally or on Server
```bash
pip install -r requirements.txt
playwright install chromium
python main.py
```
