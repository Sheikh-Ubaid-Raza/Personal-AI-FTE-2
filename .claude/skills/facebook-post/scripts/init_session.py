"""
Facebook Session Initializer — Signal-file mode (no TTY needed)
One-time headed login to save a persistent Playwright browser session.

Usage:
    python init_session.py

A Chromium window opens. Log in manually, handle any 2FA, reach the Facebook
home feed, then create the signal file to close:

    touch /tmp/fb_session_done

Session is saved to .fb_session/ and reused by post_facebook.py.
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

VAULT = Path(__file__).resolve().parent.parent.parent.parent.parent
load_dotenv(VAULT / ".env")

SESSION_DIR = Path(os.getenv("FACEBOOK_SESSION_DIR", str(VAULT / ".fb_session")))
SESSION_DIR.mkdir(parents=True, exist_ok=True)

SIGNAL_FILE = Path("/tmp/fb_session_done")
SIGNAL_FILE.unlink(missing_ok=True)
TIMEOUT_SECONDS = 300

print("=" * 60)
print("  Facebook Session Initializer")
print("=" * 60)
print(f"  Session dir  : {SESSION_DIR}")
print(f"  Signal file  : {SIGNAL_FILE}")
print()
print("  A Chromium browser window will open.")
print("  → Log in to Facebook manually")
print("  → Complete any 2FA / security check")
print("  → Once you see the HOME FEED, run:")
print()
print("       touch /tmp/fb_session_done")
print()
print(f"  You have {TIMEOUT_SECONDS // 60} minutes. Starting browser ...")
print()

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright not installed.")
    sys.exit(1)

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=str(SESSION_DIR),
        headless=False,
        slow_mo=100,
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    page.set_viewport_size({"width": 1280, "height": 900})

    print("  Navigating to facebook.com ...")
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)

    print("  Browser open — waiting for signal file ...")
    elapsed = 0
    while elapsed < TIMEOUT_SECONDS:
        if SIGNAL_FILE.exists():
            print("  Signal received! Saving session ...")
            break
        time.sleep(2)
        elapsed += 2
        if elapsed % 30 == 0:
            print(f"  Still waiting ... ({elapsed}s / {TIMEOUT_SECONDS}s)")
    else:
        print("  Timeout reached — saving session as-is.")

    browser.close()

SIGNAL_FILE.unlink(missing_ok=True)
files = list(SESSION_DIR.iterdir())
print()
print(f"  Session saved. Files in {SESSION_DIR.name}/: {len(files)}")
print("  Done.")
