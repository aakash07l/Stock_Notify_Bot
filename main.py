"""
PlayStation Gift Card Stock Monitor & Telegram Alert Bot.
Designed for 24/7 autonomous execution on Replit with resource-efficient Playwright and a keep-alive web server.
"""

import sys
import os
import json
import asyncio
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

import config

# ==========================================
# Logging Configuration
# ==========================================
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("PSNMonitor")

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# Global state tracking for keep-alive dashboard
LATEST_STOCK_STATE: Dict[str, Any] = {}
BOT_START_TIME = datetime.datetime.now()
TOTAL_CYCLES_COMPLETED = 0


# ==========================================
# State Management (Local JSON persistence)
# ==========================================
def load_state() -> Dict[str, Any]:
    """Loads previous stock status from local JSON file."""
    state_file = Path(config.STATE_FILE_PATH)
    if not state_file.exists():
        return {}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not read state file ({e}). Starting with fresh state.")
        return {}


def save_state(state: Dict[str, Any]):
    """Persists current stock status to local JSON file atomically."""
    temp_file = Path(f"{config.STATE_FILE_PATH}.tmp")
    state_file = Path(config.STATE_FILE_PATH)
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        temp_file.replace(state_file)
    except Exception as e:
        logger.error(f"Failed to persist state file: {e}")


# ==========================================
# Telegram Bot Dispatcher
# ==========================================
async def send_telegram_message(message_html: str) -> bool:
    """Helper to send any HTML formatted message to configured Telegram chat."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram Bot Token or Chat ID is missing! Skipping notification.")
        return False

    api_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(api_url, json=payload)
            if resp.status_code == 200:
                return True
            else:
                logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


async def send_startup_notification() -> bool:
    """Sends an instant confirmation message to Telegram when the bot boots up on Replit."""
    if not config.SEND_STARTUP_MESSAGE:
        return False

    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    formatted_time = now_ist.strftime("%d-%b-%Y %I:%M:%S %p IST")

    platforms_list = ", ".join([s["platform"] for s in config.TARGET_SITES if s.get("enabled", True)])

    msg = (
        f"🤖 <b>PlayStation Stock Monitor Started!</b>\n\n"
        f"📡 <b>Status:</b> 🟢 <b>Online & Running 24/7 (Railway/Cloud)</b>\n"
        f"⏱️ <b>Check Interval:</b> Every {config.CHECK_INTERVAL_SECONDS // 60} minutes\n"
        f"🎯 <b>Tracking Platforms:</b> {platforms_list}\n"
        f"⏰ <b>Started At:</b> {formatted_time}\n\n"
        f"🔄 <i>Running initial sweep now... You will receive a summary shortly!</i>"
    )
    logger.info("📤 Sending startup handshake notification to Telegram...")
    return await send_telegram_message(msg)


async def send_initial_summary_report(results: List[Dict[str, Any]]) -> bool:
    """Sends a complete stock overview report after the first cycle completes."""
    if not config.SEND_INITIAL_SUMMARY:
        return False

    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    formatted_time = now_ist.strftime("%d-%b-%Y %I:%M %p IST")

    lines = [
        f"📊 <b>Initial Stock Sweep Completed!</b>",
        f"⏰ <b>Time:</b> {formatted_time}\n",
    ]

    for item in results:
        status = item.get("status", "UNKNOWN")
        badge = "🟢 In Stock" if status == "IN_STOCK" else ("🔴 Out of Stock" if status == "OUT_OF_STOCK" else f"⚠️ {status}")
        price_str = f" ({item.get('price')})" if item.get("price") else ""
        lines.append(f"• <b>{item.get('platform')}:</b> {badge}{price_str}")

    lines.append("\n🔔 <i>Continuous restock monitoring active! You will get instant alerts the moment any card restocks.</i>")
    return await send_telegram_message("\n".join(lines))


async def send_periodic_summary_report(results: List[Dict[str, Any]], cycle_num: int) -> bool:
    """Sends a periodic live stock table update (e.g. every 2 hours)."""
    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    formatted_time = now_ist.strftime("%d-%b-%Y %I:%M %p IST")

    lines = [
        f"📊 <b>Periodic Stock Check Update (Cycle #{cycle_num})</b>",
        f"⏰ <b>Time:</b> {formatted_time}\n",
    ]

    for item in results:
        status = item.get("status", "UNKNOWN")
        badge = "🟢 In Stock" if status == "IN_STOCK" else ("🔴 Out of Stock" if status == "OUT_OF_STOCK" else f"⚠️ {status}")
        price_str = f" ({item.get('price')})" if item.get("price") else ""
        lines.append(f"• <b>{item.get('platform')}:</b> {badge}{price_str}")

    lines.append("\n✅ <i>Bot is active 24/7. Instant restock alert will trigger the moment a card restocks!</i>")
    return await send_telegram_message("\n".join(lines))


async def send_heartbeat_notification(cycle_num: int) -> bool:
    """Periodic health check notification (e.g. every 6 hours)."""
    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    formatted_time = now_ist.strftime("%d-%b-%Y %I:%M %p IST")

    msg = (
        f"💓 <b>Stock Monitor Heartbeat</b>\n\n"
        f"✅ Bot is running smoothly 24/7 in cloud.\n"
        f"🔄 <b>Cycles Completed:</b> {cycle_num}\n"
        f"⏰ <b>Timestamp:</b> {formatted_time}\n"
        f"🎯 Monitoring all {len(config.TARGET_SITES)} platforms 24/7."
    )
    return await send_telegram_message(msg)


async def send_telegram_alert(
    platform: str,
    item_name: str,
    price: str,
    url: str,
    status: str,
) -> bool:
    """Sends a formatted restock notification to Telegram Bot."""
    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    formatted_time = now_ist.strftime("%d-%b-%Y %I:%M:%S %p IST")

    message_text = (
        f"🚨 <b>RESTOCK ALERT: PlayStation Gift Card!</b>\n\n"
        f"🎮 <b>Platform:</b> {platform}\n"
        f"💳 <b>Item:</b> {item_name}\n"
        f"💰 <b>Price:</b> {price if price else 'Check Site'}\n"
        f"📦 <b>Status:</b> 🟢 <b>IN STOCK NOW!</b>\n"
        f"⏰ <b>Detected At:</b> {formatted_time}\n\n"
        f"👉 <a href='{url}'><b>CLICK HERE TO BUY NOW</b></a>\n"
    )

    logger.info(f"🚨 Dispatched Restock Alert for {item_name} on {platform}!")
    return await send_telegram_message(message_text)


# ==========================================
# Playwright & Scraping Utilities
# ==========================================
async def block_heavy_resources(route):
    """Aborts images, fonts, and media to save CPU/RAM while keeping stylesheets for Cloudflare compatibility."""
    if route.request.resource_type in ["image", "media", "font"]:
        await route.abort()
    else:
        await route.continue_()


async def check_target_playwright(context: BrowserContext, target: Dict[str, Any]) -> Dict[str, Any]:
    """Inspects a JavaScript-heavy SPA website using Playwright."""
    url = target["url"]
    wait_sel = target.get("wait_selector") or "body"
    out_keywords = [k.lower() for k in target.get("out_of_stock_keywords", [])]
    in_keywords = [k.lower() for k in target.get("in_stock_keywords", [])]
    container_sel = target.get("container_selector") or "body"
    price_sel = target.get("price_selector", "")

    page: Optional[Page] = None
    try:
        page = await context.new_page()

        if config.BLOCK_MEDIA_RESOURCES:
            await page.route("**/*", block_heavy_resources)

        try:
            # wait_until="commit" returns as soon as HTTP response begins, avoiding getting stuck on third-party tracking scripts
            await page.goto(url, timeout=config.PAGE_TIMEOUT_MS, wait_until="commit")
            await page.wait_for_timeout(3500)
        except Exception as e:
            logger.warning(f"Navigation note for {target['platform']}: {e}")

        # Extract comprehensive text content from the page
        content_text = ""
        try:
            content_text = (await page.inner_text("body")).lower()
        except Exception:
            try:
                content_text = (await page.content()).lower()
            except Exception:
                content_text = ""

        # Extract price if selector is configured
        price = ""
        if price_sel:
            try:
                price_el = page.locator(price_sel).first
                if await price_el.is_visible(timeout=2000):
                    price = (await price_el.inner_text()).strip()
            except Exception:
                price = ""

        # Determine stock status
        is_out = any(keyword in content_text for keyword in out_keywords)
        is_in = any(keyword in content_text for keyword in in_keywords)

        if is_out and not is_in:
            status = "OUT_OF_STOCK"
        elif is_in and not is_out:
            status = "IN_STOCK"
        elif is_in and is_out:
            # If both are present, priority check for clear buy indicators
            status = "IN_STOCK" if ("add to cart" in content_text or "in stock" in content_text) else "OUT_OF_STOCK"
        else:
            # If page loaded successfully (>100 chars), classify as OUT_OF_STOCK so restocks trigger properly
            status = "OUT_OF_STOCK" if len(content_text) > 100 else "UNKNOWN"

        return {
            "platform": target["platform"],
            "item_name": target["item_name"],
            "status": status,
            "price": price,
            "url": url,
            "error": None,
        }

    except Exception as e:
        logger.warning(f"Error checking {target['platform']} with Playwright: {e}")
        return {"platform": target["platform"], "item_name": target["item_name"], "status": "OUT_OF_STOCK", "price": "", "url": url, "error": str(e)}
    finally:
        if page:
            await page.close()


async def check_target_requests(target: Dict[str, Any]) -> Dict[str, Any]:
    """Inspects a website using lightweight HTTP requests and BeautifulSoup."""
    url = target["url"]
    out_keywords = [k.lower() for k in target.get("out_of_stock_keywords", [])]
    in_keywords = [k.lower() for k in target.get("in_stock_keywords", [])]
    container_sel = target.get("container_selector") or "body"
    price_sel = target.get("price_selector", "")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {"platform": target["platform"], "item_name": target["item_name"], "status": "ERROR", "price": "", "url": url, "error": f"HTTP {resp.status_code}"}

            soup = BeautifulSoup(resp.text, "html.parser")

            container_el = soup.select(container_sel) if container_sel else []
            if container_el:
                content_text = " ".join([el.get_text() for el in container_el]).lower()
            else:
                content_text = soup.get_text().lower()

            price = ""
            if price_sel:
                price_match = soup.select_one(price_sel)
                if price_match:
                    price = price_match.get_text().strip()

            is_out = any(keyword in content_text for keyword in out_keywords)
            is_in = any(keyword in content_text for keyword in in_keywords)

            if is_out and not is_in:
                status = "OUT_OF_STOCK"
            elif is_in and not is_out:
                status = "IN_STOCK"
            elif is_in and is_out:
                status = "IN_STOCK" if "add to cart" in content_text or "in stock" in content_text else "OUT_OF_STOCK"
            else:
                status = "OUT_OF_STOCK" if is_out else "UNKNOWN"

            return {
                "platform": target["platform"],
                "item_name": target["item_name"],
                "status": status,
                "price": price,
                "url": url,
                "error": None,
            }

    except Exception as e:
        logger.warning(f"Error checking {target['platform']} with HTTP requests: {e}")
        return {"platform": target["platform"], "item_name": target["item_name"], "status": "ERROR", "price": "", "url": url, "error": str(e)}


# ==========================================
# Keep-Alive HTTP Server & Live Dashboard (for UptimeRobot)
# ==========================================
async def start_keep_alive_server():
    """Serves a modern live status dashboard on port 8080 for UptimeRobot to ping."""
    async def handle_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            await reader.read(1024)
            uptime_seconds = int((datetime.datetime.now() - BOT_START_TIME).total_seconds())
            hours, remainder = divmod(uptime_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours}h {minutes}m {seconds}s"

            now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
            formatted_time = now_ist.strftime("%d-%b-%Y %I:%M:%S %p IST")

            # Build HTML rows for live state
            rows_html = ""
            for item_id, item_data in LATEST_STOCK_STATE.items():
                status = item_data.get("status", "PENDING")
                badge_class = "badge-in" if status == "IN_STOCK" else ("badge-out" if status == "OUT_OF_STOCK" else "badge-warn")
                badge_text = "IN STOCK" if status == "IN_STOCK" else ("OUT OF STOCK" if status == "OUT_OF_STOCK" else status)
                rows_html += f"""
                <tr>
                    <td><strong>{item_data.get('platform', '')}</strong></td>
                    <td>{item_data.get('item_name', '')}</td>
                    <td><span class="badge {badge_class}">{badge_text}</span></td>
                    <td>{item_data.get('last_price', 'N/A')}</td>
                    <td><a href="{item_data.get('url', '#')}" target="_blank" class="buy-link">Open Store ↗</a></td>
                </tr>
                """

            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PSN Gift Card Stock Monitor</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }}
        .card {{ max-width: 800px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        h1 {{ font-size: 24px; margin-top: 0; display: flex; align-items: center; gap: 10px; }}
        .pulse {{ display: inline-block; width: 12px; height: 12px; background: #22c55e; border-radius: 50%; box-shadow: 0 0 10px #22c55e; }}
        .stats {{ display: flex; gap: 16px; margin-bottom: 24px; font-size: 14px; color: #94a3b8; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: #0f172a; color: #cbd5e1; font-weight: 600; }}
        .badge {{ padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: bold; }}
        .badge-in {{ background: #15803d; color: #dcfce7; }}
        .badge-out {{ background: #991b1b; color: #fee2e2; }}
        .badge-warn {{ background: #854d0e; color: #fef9c3; }}
        .buy-link {{ color: #38bdf8; text-decoration: none; font-weight: 500; }}
        .buy-link:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="card">
        <h1><span class="pulse"></span> PlayStation Stock Monitor (24/7 Active)</h1>
        <div class="stats">
            <div>⏱️ <strong>Uptime:</strong> {uptime_str}</div>
            <div>🔄 <strong>Cycles:</strong> {TOTAL_CYCLES_COMPLETED}</div>
            <div>⏰ <strong>Last Checked:</strong> {formatted_time}</div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Platform</th>
                    <th>Item</th>
                    <th>Status</th>
                    <th>Price</th>
                    <th>Store Link</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="5" style="text-align:center; padding:20px; color:#94a3b8;">Initial sweep in progress... Refresh in a few seconds.</td></tr>'}
            </tbody>
        </table>
    </div>
</body>
</html>"""

            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(html_content.encode('utf-8'))}\r\n"
                "Connection: close\r\n"
                "\r\n"
                + html_content
            )
            writer.write(response.encode("utf-8"))
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    try:
        server = await asyncio.start_server(handle_request, "0.0.0.0", config.KEEP_ALIVE_PORT)
        logger.info(f"🌐 Keep-Alive dashboard server listening on http://0.0.0.0:{config.KEEP_ALIVE_PORT}")
        return server
    except Exception as e:
        logger.warning(f"Could not bind Keep-Alive server to port {config.KEEP_ALIVE_PORT}: {e}")
        return None


# ==========================================
# Main Monitoring Cycle
# ==========================================
async def run_monitor_cycle(browser: Optional[Browser], context: Optional[BrowserContext], state: Dict[str, Any], is_first_cycle: bool):
    """Performs one full sweep over all configured target websites."""
    global TOTAL_CYCLES_COMPLETED, LATEST_STOCK_STATE
    TOTAL_CYCLES_COMPLETED += 1

    logger.info("=" * 60)
    logger.info(f"🔍 Starting stock check sweep #{TOTAL_CYCLES_COMPLETED} at {datetime.datetime.now().strftime('%H:%M:%S')}...")

    cycle_results: List[Dict[str, Any]] = []

    for target in config.TARGET_SITES:
        if not target.get("enabled", True):
            continue

        target_id = target["id"]
        platform = target["platform"]
        item_name = target["item_name"]
        url = target["url"]
        engine = target.get("engine", "playwright").lower()

        logger.info(f"Checking [{platform}] - {item_name} (via {engine})...")

        result = {}
        if engine == "playwright" and context:
            result = await check_target_playwright(context, target)
        else:
            result = await check_target_requests(target)

        current_status = result.get("status", "UNKNOWN")
        price = result.get("price", "")
        cycle_results.append(result)

        previous_data = state.get(target_id, {})
        previous_status = previous_data.get("status")

        icon = "🟢 IN STOCK" if current_status == "IN_STOCK" else ("🔴 OUT OF STOCK" if current_status == "OUT_OF_STOCK" else "⚠️ " + current_status)
        logger.info(f"  -> Result: {icon} | Price: {price if price else 'N/A'}")

        # Update global state for web dashboard
        LATEST_STOCK_STATE[target_id] = {
            "platform": platform,
            "item_name": item_name,
            "status": current_status,
            "last_price": price,
            "url": url,
            "last_checked": datetime.datetime.now().isoformat(),
        }

        # Check for Alert Triggers
        should_alert = False

        # Condition 1: Out of Stock -> In Stock transition
        if previous_status == "OUT_OF_STOCK" and current_status == "IN_STOCK":
            logger.info(f"🚨 Restock transition detected for {item_name} on {platform}!")
            should_alert = True
        # Condition 2: Initial Run In-Stock alert (if enabled)
        elif previous_status is None and current_status == "IN_STOCK" and config.NOTIFY_ON_INITIAL_RUN:
            logger.info(f"📢 Initial In-Stock detected for {item_name} on {platform}!")
            should_alert = True

        if should_alert:
            await send_telegram_alert(
                platform=platform,
                item_name=item_name,
                price=price,
                url=url,
                status=current_status,
            )

        # Update persistent local state
        if current_status != "ERROR":
            state[target_id] = {
                "platform": platform,
                "item_name": item_name,
                "status": current_status,
                "last_price": price,
                "last_checked": datetime.datetime.now().isoformat(),
            }
            save_state(state)

        # Gentle delay between sites
        await asyncio.sleep(config.SITE_CHECK_DELAY_SECONDS)

    # If first cycle, dispatch summary report to Telegram so user has 100% visibility
    if is_first_cycle:
        logger.info("📤 Sending initial summary overview to Telegram...")
        await send_initial_summary_report(cycle_results)
    elif config.PERIODIC_SUMMARY_CYCLES > 0 and TOTAL_CYCLES_COMPLETED % config.PERIODIC_SUMMARY_CYCLES == 0:
        logger.info(f"📤 Sending periodic stock update (Cycle #{TOTAL_CYCLES_COMPLETED}) to Telegram...")
        await send_periodic_summary_report(cycle_results, TOTAL_CYCLES_COMPLETED)

    # Periodic heartbeat notification (e.g. every 90 cycles)
    if config.HEARTBEAT_CYCLE_INTERVAL > 0 and TOTAL_CYCLES_COMPLETED % config.HEARTBEAT_CYCLE_INTERVAL == 0:
        logger.info("📤 Sending periodic heartbeat to Telegram...")
        await send_heartbeat_notification(TOTAL_CYCLES_COMPLETED)

    logger.info("🏁 Stock check sweep complete. Resting until next interval.")


# ==========================================
# Main Application Entry Point
# ==========================================
async def main():
    logger.info("=" * 60)
    logger.info("🚀 PlayStation Gift Card Monitor starting up...")
    logger.info(f"⏱️ Check Interval: {config.CHECK_INTERVAL_SECONDS} seconds")
    logger.info(f"📱 Telegram Alerts: {'Configured' if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID else 'NOT CONFIGURED'}")
    logger.info("=" * 60)

    # Start Keep-Alive Web Server for UptimeRobot
    await start_keep_alive_server()

    # Dispatch Startup Handshake to Telegram
    await send_startup_notification()

    state = load_state()

    playwright_instance = None
    browser = None
    context = None

    try:
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--no-zygote",
                "--single-process",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        logger.info("🌐 Playwright Headless Chromium successfully initialized.")
    except Exception as e:
        logger.error(f"Failed to start Playwright browser: {e}")
        logger.error("Continuing in fallback HTTP-only mode. Ensure 'playwright install chromium' is run.")

    is_first = True
    try:
        while True:
            try:
                await run_monitor_cycle(browser, context, state, is_first_cycle=is_first)
                is_first = False
            except Exception as e:
                logger.error(f"Unexpected error during monitor cycle #{TOTAL_CYCLES_COMPLETED}: {e}", exc_info=True)

            logger.info(f"💤 Sleeping for {config.CHECK_INTERVAL_SECONDS}s before next check...\n")
            await asyncio.sleep(config.CHECK_INTERVAL_SECONDS)

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("🛑 Shutting down PlayStation Stock Monitor...")
    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if playwright_instance:
            await playwright_instance.stop()
        logger.info("👋 Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
