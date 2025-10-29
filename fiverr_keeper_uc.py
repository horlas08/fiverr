import os
import time
import json
import smtplib
import requests
import undetected_chromedriver as uc
from email.mime.text import MIMEText
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException

# ----------------------------------------------------------
# CONFIG
# ----------------------------------------------------------
FIVERR_DASHBOARD_URL = "https://www.fiverr.com/seller_dashboard"
COOKIES_FILE = "cookies.json"
PROFILE_DIR = os.path.expanduser("~/.config/fiverr_chrome")
SCREENSHOT_DIR = "screenshots"
CHECK_INTERVAL = 60 * 5  # check every 5 minutes
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

# Email alert config
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO")
ALERT_EMAIL_FROM = SMTP_USER

# Telegram (optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ----------------------------------------------------------
# HELPER FUNCTIONS
# ----------------------------------------------------------
def send_email_notification(subject, body):
    if not SMTP_USER or not ALERT_EMAIL_TO:
        print("[email] skipped (SMTP_USER or ALERT_EMAIL_TO not set)")
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = ALERT_EMAIL_FROM
        msg["To"] = ALERT_EMAIL_TO
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(ALERT_EMAIL_FROM, [ALERT_EMAIL_TO], msg.as_string())
        print("[email] alert sent.")
    except Exception as e:
        print("[email] failed:", e)

def notify_telegram(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        print("[telegram] notified")
    except Exception as e:
        print("[telegram] failed:", e)

def save_screenshot(driver, name):
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    # path = os.path.join(SCREENSHOT_DIR, f"{name}_{int(time.time())}.png")
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    driver.save_screenshot(path)
    print("[screenshot] saved:", path)

def backup_cookies(driver):
    try:
        cookies = driver.get_cookies()
        with open("cookies_backup.json", "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
        print("[cookies] backed up.")
    except Exception as e:
        print("[cookies] backup failed:", e)

# ----------------------------------------------------------
# BROWSER SETUP
# ----------------------------------------------------------
def setup_driver():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    opts = uc.ChromeOptions()
    opts.headless = HEADLESS
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    driver = uc.Chrome(options=opts)
    driver.set_page_load_timeout(60)
    return driver

# ----------------------------------------------------------
# HEALTH CHECKS
# ----------------------------------------------------------
def is_challenge_page(driver):
    try:
        page = driver.page_source.lower()
        indicators = ["press & hold", "verify you are human", "perimeterx", "px", "needs a human touch"]
        return any(i in page for i in indicators)
    except:
        return True

def get_unread_counts(driver):
    unread_notifications_url = "https://www.fiverr.com/notification_items/unread_count"
    unread_messages_url = "https://www.fiverr.com/inbox/counters/unread"
    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()
    # copy cookies from browser to requests
    for c in driver.get_cookies():
        session.cookies.set(c["name"], c["value"], domain=c["domain"])
    notif_count = 0
    inbox_count = 0
    try:
        notif_resp = session.get(unread_notifications_url, headers=headers, timeout=10)
        inbox_resp = session.get(unread_messages_url, headers=headers, timeout=10)
        notif_count = notif_resp.json().get("count", 0)
        inbox_count = inbox_resp.json().get("count", 0)
    except Exception as e:
        print("[health] unread count failed:", e)
    return notif_count, inbox_count

def health_check(driver):
    if is_challenge_page(driver):
        return False, "Press & Hold challenge detected", 0, 0
    notif, inbox = get_unread_counts(driver)
    return True, "OK", notif, inbox

def health_check_and_recover(driver):
    ok, msg, notif, inbox = health_check(driver)
    if ok:
        return True, notif, inbox

    print("[health] fail:", msg)
    save_screenshot(driver, "challenge_detected")
    send_email_notification("Fiverr Keeper Alert", msg)
    notify_telegram(msg)

    # try refresh a few times
    for _ in range(3):
        try:
            driver.refresh()
            time.sleep(5)
            if not is_challenge_page(driver):
                print("[health] recovered after refresh")
                backup_cookies(driver)
                return True, *get_unread_counts(driver)
        except WebDriverException:
            pass

    # headful manual solve recovery
    try:
        print("[health] opening headful Chrome for manual solve")
        driver.quit()
        opts = uc.ChromeOptions()
        opts.headless = False
        opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
        vis = uc.Chrome(options=opts)
        vis.get("https://www.fiverr.com/")
        print("[recovery] please solve the challenge manually.")
        end = time.time() + 180
        while time.time() < end:
            if not is_challenge_page(vis):
                backup_cookies(vis)
                save_screenshot(vis, "recovered_manual")
                vis.quit()
                return True, *get_unread_counts(driver)
            time.sleep(5)
        vis.quit()
    except Exception as e:
        print("[recovery] failed:", e)

    return False, notif, inbox



# ----------------------------------------------------------
# MAIN LOOP
# ----------------------------------------------------------
def main():
    driver = setup_driver()
    driver.get(FIVERR_DASHBOARD_URL)
    backup_cookies(driver)
    print("[init] Fiverr dashboard loaded")
    REFRESH_INTERVAL = 60 * 60 * 4  # every 4 hours
    last_refresh = time.time()
    while True:
        ok, notif, inbox = health_check_and_recover(driver)
        print(f"[loop] ok={ok}, notif={notif}, inbox={inbox}")
        # Auto-refresh every few hours to simulate activity
        if time.time() - last_refresh > REFRESH_INTERVAL:
            print("[loop] refreshing Fiverr page to keep session fresh...")
            driver.refresh()
            time.sleep(10)
            last_refresh = time.time()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
