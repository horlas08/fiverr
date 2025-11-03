#!/usr/bin/env python3
"""
Fiverr Keeper VPS Version (Linux Compatible)
- Uses SeleniumBase UC Mode instead of undetected-chromedriver
- Persistent user-data-dir so PX solved challenge persists
- Handles headless mode for VPS
- Takes screenshots, checks unread counters
- Sends email & optional Telegram alerts on new unreads
"""

import os
import time
import json
import traceback
import smtplib
import requests
import os, sys, psutil
from email.message import EmailMessage
from bs4 import BeautifulSoup
# from selenium.common.exceptions import WebDriverException
from dotenv import load_dotenv
from seleniumbase import SB, Driver

# ----------------------------------------------------------
# Load environment
# ----------------------------------------------------------
load_dotenv()

COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.json")
FIVERR_DASH = os.getenv("FIVERR_DASH", "https://www.fiverr.com/seller_dashboard")
NOTIF_URL = "https://www.fiverr.com/notification_items/unread_count"
INBOX_URL = "https://www.fiverr.com/inbox/counters/unread"

HEADLESS = os.getenv("HEADLESS", "true").lower() in ("1", "true", "yes", "y")
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "10"))
REFRESH_INTERVAL_HOURS = float(os.getenv("REFRESH_INTERVAL_HOURS", "3"))
PROFILE_DIR = os.getenv("PROFILE_DIR", os.path.expanduser("~/.config/fiverr_profiles"))
SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", "./screenshots")

# Email config
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT")
SMTP_FROM = os.getenv("SMTP_FROM")
SMTP_TO = os.getenv("SMTP_TO")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "true").lower() in ("1", "true", "yes", "y")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "false").lower() in ("1", "true", "yes", "y")

# Telegram (optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

last_alert_unreads = 0


# ----------------------------------------------------------
# Notification functions
# ----------------------------------------------------------
def send_email_notification(subject: str, body: str) -> None:
    print(body)
    if not (SMTP_HOST and SMTP_PORT and SMTP_FROM and SMTP_TO):
        print("[email] SMTP not configured, skipping:", subject)
        return
    try:
        msg = EmailMessage()
        msg["From"] = SMTP_FROM
        msg["To"] = SMTP_TO
        msg["Subject"] = subject
        msg.set_content(body)
        port_i = int(SMTP_PORT)
        if SMTP_USE_SSL:
            with smtplib.SMTP_SSL(SMTP_HOST, port_i) as smtp:
                if SMTP_USER and SMTP_PASSWORD:
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, port_i) as smtp:
                smtp.ehlo()
                if SMTP_USE_TLS:
                    smtp.starttls()
                if SMTP_USER and SMTP_PASSWORD:
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
        print("[email] Sent:", subject)
    except Exception as e:
        print("[email] Failed:", e)


def notify_telegram(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        print("[telegram] notified")
    except Exception as e:
        print("[telegram] failed:", e)


# ----------------------------------------------------------
# Helper functions
# ----------------------------------------------------------
def save_screenshot(driver, prefix="fiverr"):
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    ts = int(time.time())
    path = os.path.join(SCREENSHOT_DIR, f"{prefix}_{ts}.png")
    try:
        driver.save_screenshot(path)
        print("[screenshot] saved:", path)
    except Exception as e:
        print("[screenshot] failed:", e)


def extract_json_from_page_source(src_text):
    try:
        soup = BeautifulSoup(src_text, "html.parser")
        pre = soup.find("pre")
        if pre and pre.get_text().strip().startswith("{"):
            return pre.get_text().strip()
    except Exception:
        pass
    start = src_text.find("{")
    end = src_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return src_text[start:end + 1]
    return None


def load_cookies(driver):
    # We will not forcibly add cookies if using user-data-dir profile,
    # but we still support loading cookies.json if present (for first-run)
    if os.path.exists(COOKIES_FILE):
        print("[cookies] cookies.json found. Adding cookies into profile (may override).")
        driver.get("https://www.fiverr.com/")
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for c in cookies:
            cookie = {k: v for k, v in c.items() if v is not None}
            if "expirationDate" in cookie:
                cookie["expires"] = int(cookie.pop("expirationDate"))
            if "expiry" in cookie:
                cookie["expires"] = int(cookie.pop("expiry"))
            cookie.setdefault("path", "/")
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                print("[cookies] skip:", cookie.get("name"), e)
        driver.refresh()
        time.sleep(1)
        print("[cookies] loaded into profile.")
    else:
        print("[cookies] cookies.json not found — relying on profile data if present.")


# ----------------------------------------------------------
# Browser setup (SeleniumBase UC Mode)
# ----------------------------------------------------------
def setup_driver():
    os.makedirs(PROFILE_DIR, exist_ok=True)

    # driver = Driver(
    #     uc=True,
    #     uc_subprocess=True,
    #     enable_ws=True,
    #     headless=True,
    #     headless1=True,
    #     headless2=True,
    #     disable_gpu=False,
    #      agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    #       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    #      chromium_arg="--disable-background-timer-throttling,"
    #              "--disable-backgrounding-occluded-windows,"
    #              "--disable-background-networking,"
    #              "--no-sandbox"
    #     # headless=HEADLESS,
    #     # undetectable=True,
    #     # user_data_dir=PROFILE_DIR,
    #     # incognito=False,
    #     # no_sandbox=True,
    #     # disable_gpu=True,
    #     # disable_dev_shm_usage=True,
    #     # window_size="1600,1000",
    #     # agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    #     #       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # )

    print("[driver] SeleniumBase UC mode started")
    driver.set_page_load_timeout(60)

    try:
        driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """)
    except Exception:
        pass

    return driver


# ----------------------------------------------------------
# Core logic
# ----------------------------------------------------------
def get_unread_counts(driver):
    driver.get(NOTIF_URL)
    time.sleep(1)
    notif_json = extract_json_from_page_source(driver.page_source)
    notif = json.loads(notif_json) if notif_json else {}
    n = int(notif.get("count", 0))

    driver.get(INBOX_URL)
    time.sleep(1)
    inbox_json = extract_json_from_page_source(driver.page_source)
    inbox = json.loads(inbox_json) if inbox_json else {}
    m = int(inbox.get("count", 0))

    return n, m


def main():

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        if "fiverr_keeper_sb.py" in " ".join(proc.info.get("cmdline", [])) and proc.pid != os.getpid():
            print("Another Fiverr bot is already running — exiting.")
            sys.exit(0)
    global last_alert_unreads
    driver = None
    try:
        os.environ["SB_HEADLESS_MODE"] = "1" if HEADLESS else "0"
        os.environ["DISPLAY"] = ":99"
        # driver = setup_driver()
        with SB(uc=True,
                headless=HEADLESS,  # Respect your env var
                xvfb=True,  # Run in virtual display

                block_images=True,  # Saves network and memory
                incognito=False,
                disable_csp=True,  # Prevents CSP issues
                ad_block_on=True,  # Reduce background ad activity
                swiftshader=True,  # Use software rendering (lighter)
                user_data_dir=PROFILE_DIR,
                chromium_arg="--no-sandbox --disable-dev-shm-usage --disable-gpu --remote-debugging-port=9222 --mute-audio --window-size=1280,800",
                # chromium_arg=(
                #     "--no-sandbox "
                #     "--disable-gpu "
                #     "--disable-dev-shm-usage "
                #     "--mute-audio "
                #     "--disable-background-timer-throttling "
                #     "--disable-extensions "
                #     "--disable-software-rasterizer "
                #     "--disable-backgrounding-occluded-windows "
                #  ),
                # disable_features="TranslateUI,BlinkGenPropertyTrees",
                # start_page="https://www.fiverr.com/",
                # window_size="1280,800",
                agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", ) as sb:
            driver = sb.driver
            # sb.uc_gui_press_key()
            sb.uc_open_with_reconnect("https://www.fiverr.com/", 4)
            sb.uc_gui_handle_captcha()
            print("[driver] started. Profile dir:", PROFILE_DIR)
            # driver.get("https://www.fiverr.com/")
            time.sleep(2)
            load_cookies(sb.driver)
            # driver
            sb.get(FIVERR_DASH)

            time.sleep(1)
            sb.execute_script("""
                setInterval(() => {
                    if (window.WebSocket) {
                         const sockets = [];
                         for (let k in window) {
                          if (window[k] instanceof WebSocket) sockets.push(window[k]);
                         }
                  sockets.forEach(s => {
                      if (s.readyState === 1) s.send('ping');
                     });
                 }
                }, 50000); // every 50 seconds
            """)
            save_screenshot(sb.driver, "startup")

            try:
                n, m = get_unread_counts(sb.driver)
                print("[init] notif:", n, "msgs:", m)
            except Exception as e:
                save_screenshot(sb.driver, "initial_check_failed")
                raise Exception("Initial unread check failed: " + repr(e))

            last_refresh = time.time()

            while True:
                try:
                    n, m = get_unread_counts(sb.driver)
                    total = n + m
                    print("[poll] notif:", n, "msgs:", m, "total:", total)

                    if total == 0 and last_alert_unreads != 0:
                        print("[tracker] all read -> reset last_alert_unreads")
                        last_alert_unreads = 0

                    if total > last_alert_unreads:
                        subject = "Fiverr: New notifications/messages"
                        body = f"Unread Notifications: {n}\nUnread Messages: {m}\nTotal: {total}\nTime: {time.ctime()}"
                        send_email_notification(subject, body)
                        notify_telegram(body)
                        last_alert_unreads = total

                    if time.time() - last_refresh >= REFRESH_INTERVAL_HOURS * 3600:
                        print("[refresh] refreshing dashboard to keep WS alive")
                        sb.get(FIVERR_DASH)
                        time.sleep(4)
                        save_screenshot(sb.driver, "refresh")
                        last_refresh = time.time()

                    time.sleep(HEARTBEAT_INTERVAL)
                except Exception as inner:
                    save_screenshot(sb.driver, "poll_error")
                    print("[loop error]", inner)
                    traceback.print_exc()
                    time.sleep(10)
    except Exception as e:
        tb = traceback.format_exc()
        print("[fatal]", e)
        print(tb)
        if driver:
            save_screenshot(driver, "fatal")
        send_email_notification("Fiverr Keeper: Fatal error", f"{e}\n\n{tb}")
        notify_telegram(f"Fiverr Keeper fatal error: {e}")
        raise
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
