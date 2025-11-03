#!/usr/bin/env python3
"""
Fiverr Keeper with undetected-chromedriver + persistent profile (Windows friendly)
- Uses undetected-chromedriver
- Uses persistent user-data-dir so solved PX challenge persists
- Headful by default for first-run; toggle HEADLESS env var for headless
- Takes screenshots, checks unread counters, sends email on new unreads
"""

import os
import time
import json
import traceback
import smtplib
from email.message import EmailMessage
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# load env
load_dotenv()

COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.json")
FIVERR_DASH = os.getenv("FIVERR_DASH", "https://www.fiverr.com/seller_dashboard")
NOTIF_URL = "https://www.fiverr.com/notification_items/unread_count"
INBOX_URL = "https://www.fiverr.com/inbox/counters/unread"

# Behavior settings
HEADLESS = os.getenv("HEADLESS", "false").lower() in ("1","true","yes","y")
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "10"))
REFRESH_INTERVAL_HOURS = int(os.getenv("REFRESH_INTERVAL_HOURS", "3"))
PROFILE_DIR = os.getenv("PROFILE_DIR", os.path.expanduser("~/fiverr_profile"))
SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", ".")

# Email settings
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT")
SMTP_FROM = os.getenv("SMTP_FROM")
SMTP_TO = os.getenv("SMTP_TO")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "true").lower() in ("1","true","yes","y")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "false").lower() in ("1","true","yes","y")

last_alert_unreads = 0

def send_email_notification(subject: str, body: str) -> None:

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
        return src_text[start:end+1]
    return None

def get_unread_counts(driver):
    driver.get(NOTIF_URL)
    time.sleep(0.6)
    notif_json = extract_json_from_page_source(driver.page_source)
    if not notif_json:
        raise Exception("No JSON from notification_items/unread_count")
    notif = json.loads(notif_json)
    notif_count = int(notif.get("count", 0))

    driver.get(INBOX_URL)
    time.sleep(0.6)
    inbox_json = extract_json_from_page_source(driver.page_source)
    if not inbox_json:
        raise Exception("No JSON from inbox/counters/unread")
    inbox = json.loads(inbox_json)
    inbox_count = int(inbox.get("count", 0))

    return notif_count, inbox_count

def setup_driver():
    import undetected_chromedriver as uc
    # ensure profile dir exists
    os.makedirs(PROFILE_DIR, exist_ok=True)

    options = uc.ChromeOptions()
    # Use profile dir so cookies/localStorage persist
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    # optional: specialise profile for this script
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-dev-shm-usage")
    # options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1600,1000")
    # user-agent
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    # headless support in undetected_chromedriver
    uc_headless = HEADLESS
    driver = uc.Chrome(options=options, headless=uc_headless)
    # inject some JS to mask webdriver property (redundant but safe)
    try:
        driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """)
    except Exception:
        pass
    return driver

def load_cookies(driver):
    # We will not forcibly add cookies if using user-data-dir profile,
    # but we still support loading cookies.json if present (for first-run)
    if os.path.exists(COOKIES_FILE):
        print("[cookies] cookies.json found. Adding cookies into profile (may override).")
        driver.get("https://www.fiverr.com/")
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for c in cookies:
            cookie = {k:v for k,v in c.items() if v is not None}
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

def main():
    global last_alert_unreads
    driver = None
    try:
        driver = setup_driver()
        print("[driver] started. Profile dir:", PROFILE_DIR)
        # Open Fiverr root first to allow PX to run if needed
        driver.get("https://www.fiverr.com/")
        time.sleep(1)
        # optional: if you have cookies.json, load them
        load_cookies(driver)

        # If first time, do not go headless until you manually solve challenge
        driver.get(FIVERR_DASH)
        time.sleep(6)
        save_screenshot(driver, "startup")

        # check initial unread counters
        try:
            n, m = get_unread_counts(driver)
            print("[init] notif:", n, "msgs:", m)
        except Exception as e:
            save_screenshot(driver, "initial_check_failed")
            raise Exception("Initial unread check failed: " + repr(e))

        last_refresh = time.time()
        while True:
            try:
                n, m = get_unread_counts(driver)
                total = n + m
                print("[poll] notif:", n, "msgs:", m, "total:", total)

                if total == 0 and last_alert_unreads != 0:
                    print("[tracker] all read -> reset last_alert_unreads")
                    last_alert_unreads = 0

                if total > last_alert_unreads:
                    subject = "Fiverr: New notifications/messages"
                    body = f"Unread Notifications: {n}\nUnread Messages: {m}\nTotal: {total}\nTime: {time.ctime()}"
                    send_email_notification(subject, body)
                    last_alert_unreads = total

                if time.time() - last_refresh >= REFRESH_INTERVAL_HOURS * 3600:
                    print("[refresh] refreshing dashboard to keep WS alive")
                    driver.get(FIVERR_DASH)
                    time.sleep(4)
                    save_screenshot(driver, "refresh")
                    last_refresh = time.time()

                time.sleep(HEARTBEAT_INTERVAL)
            except Exception as inner:
                save_screenshot(driver, "poll_error")
                raise

    except Exception as e:
        tb = traceback.format_exc()
        print("[fatal]", e)
        print(tb)
        try:
            if driver:
                save_screenshot(driver, "fatal")
        except Exception:
            pass
        send_email_notification("Fiverr Keeper: Fatal error", f"{e}\n\nTraceback:\n{tb}")
        raise
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

if __name__ == "__main__":
    main()