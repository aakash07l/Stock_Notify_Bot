# 🎮 PlayStation Gift Card Stock Monitor & Telegram Alert Bot (Replit Ready)

Autonomous, lightweight Python stock monitoring bot designed for 24/7 execution on Replit. Monitors PlayStation (India) gift card availability across **Rooter, Games The Shop, JioGames, Hubble, and MX2Games**, sending instant alerts to your Telegram bot whenever an item restocks from **Out of Stock** to **In Stock**.

---

## 📁 Project Structure

```text
ps_stock_monitor/
├── main.py              # Core asynchronous runner, Playwright scraper, keep-alive server & Telegram notifier
├── config.py            # Clean target website configuration, URLs, CSS selectors & loop settings
├── requirements.txt     # Python dependencies (playwright, httpx, beautifulsoup4, python-dotenv)
├── .env.example         # Example environment variables
├── replit.nix           # Nix system libraries required for Headless Chromium on Replit
├── .replit              # Replit run instructions & web port bindings
└── stock_state.json     # Auto-generated local state file to track stock transitions
```

---

## 🚀 Replit Deployment Guide (Step-by-Step)

### Step 1: Create a New Repl
1. Log in to [Replit](https://replit.com).
2. Click **+ Create Repl**.
3. Select **Python** as the template.
4. Name your Repl (e.g., `psn-card-monitor`).

### Step 2: Upload or Create the Project Files
Copy and paste the files into your Repl:
- `main.py`
- `config.py`
- `requirements.txt`
- `replit.nix` (In Replit, click the three dots in the Files panel -> **Show Hidden Files** -> edit `replit.nix`)
- `.replit`

### Step 3: Configure Replit Secrets (Environment Variables)
Never paste API tokens directly in code. Use Replit's built-in Secret Manager:
1. In your Repl sidebar, click on **Tools** -> **Secrets** (or the Lock 🔒 icon).
2. Add the following secrets:
   - `TELEGRAM_BOT_TOKEN`: Your Telegram Bot API token from [@BotFather](https://t.me/BotFather).
   - `TELEGRAM_CHAT_ID`: Your numerical Telegram Chat ID (obtain via [@userinfobot](https://t.me/userinfobot)).
   - `CHECK_INTERVAL_SECONDS`: `240` (or your preferred interval in seconds, e.g. 180 to 300).
   - `NOTIFY_ON_INITIAL_RUN`: `False` (set to `True` if you want an alert right now for items currently in stock).

### Step 4: Install Dependencies & Playwright Chromium
Open the **Shell** tab in Replit and run:

```bash
pip install -r requirements.txt
playwright install chromium
```

> **Note on Linux Libraries:** Because `replit.nix` includes `glib`, `nss`, `atk`, `gtk3`, and `pango`, Chromium will run seamlessly without missing `.so` library errors!

### Step 5: Start the Bot
Click the big green **Run** button or execute in the Shell:
```bash
python main.py
```
You will see output indicating that:
1. The Keep-Alive web server started on port `8080`.
2. Playwright Headless Chromium initialized.
3. The stock sweep began across all configured platforms.

---

## ⏰ Keeping the Bot Running 24/7 with UptimeRobot (Free)

Replit containers put free Repls to sleep if they do not receive inbound web traffic. `main.py` includes a lightweight built-in HTTP server listening on port `8080` specifically for this purpose.

1. Once your Repl is running, look at the built-in **Webview panel** in Replit.
2. Copy your Repl's public URL (e.g., `https://psn-card-monitor.<your-replit-username>.repl.co`).
3. Create a free account at [UptimeRobot](https://uptimerobot.com).
4. Click **Add New Monitor**:
   - **Monitor Type:** `HTTP(s)`
   - **Friendly Name:** `PlayStation Stock Monitor`
   - **URL (or IP):** Paste your Repl's web URL.
   - **Monitoring Interval:** `5 minutes`
5. Click **Create Monitor**.
UptimeRobot will ping your Repl every 5 minutes, keeping it awake indefinitely!
