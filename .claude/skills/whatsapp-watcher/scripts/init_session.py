"""
AI Employee — WhatsApp Session Initializer
Launches WhatsApp Web in visible mode so you can scan the QR code
with your phone to authenticate and save the session.

Usage:
    python init_session.py
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# ── Paths ────────────────────────────────────────────────────────────
VAULT = Path(__file__).resolve().parent.parent.parent.parent.parent
SESSION_DIR = VAULT / ".wa_session"

# ── Config ──────────────────────────────────────────────────────────
HEADLESS = os.getenv("WHATSAPP_HEADLESS", "false").lower() == "true"

def main():
    # Ensure session directory exists
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    
    print()
    print("=" * 60)
    print("  AI EMPLOYEE — WHATSAPP SESSION INITIALIZER")
    print("=" * 60)
    print()
    print("  This will launch WhatsApp Web in a browser window.")
    print()
    print("  INSTRUCTIONS:")
    print("  1. Wait for the QR code to appear")
    print("  2. Open WhatsApp on your phone")
    print("  3. Go to Settings > Linked Devices > Link a Device")
    print("  4. Scan the QR code with your phone")
    print("  5. Wait for WhatsApp to load (session saved automatically)")
    print("  6. Close the browser window")
    print()
    print(f"  Session will be saved to: {SESSION_DIR}")
    print()
    print("  Press Ctrl+C to cancel")
    print()
    input("  Press ENTER to continue...")
    print()
    
    try:
        with sync_playwright() as p:
            # Launch browser with persistent context (visible mode)
            print("  Launching browser...")
            context = p.chromium.launch_persistent_context(
                str(SESSION_DIR),
                headless=False,  # Visible for QR scanning
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--window-size=1280,800',
                ]
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            print("  Navigating to WhatsApp Web...")
            page.goto('https://web.whatsapp.com', wait_until='domcontentloaded')
            
            print()
            print("  ✓ Browser is now open")
            print()
            print("  Waiting for you to scan the QR code...")
            print("  (This window will stay open for 5 minutes)")
            print()
            
            # Wait for user to scan QR and WhatsApp to load
            # Check for main chat list (indicates successful login)
            max_wait = 300  # 5 minutes
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                try:
                    # Check if chat list is visible (logged in)
                    chat_list = page.query_selector('[data-testid="chat-list"]')
                    if chat_list:
                        print()
                        print("  ✓ WhatsApp Web loaded successfully!")
                        print("  ✓ Session saved to:", SESSION_DIR)
                        print()
                        print("  You can now close this window.")
                        print("  The WhatsApp Watcher will use this saved session.")
                        print()
                        
                        # Wait a bit more to ensure session is fully saved
                        time.sleep(3)
                        break
                except Exception:
                    pass
                
                time.sleep(1)
            
            context.close()
            
            print()
            print("=" * 60)
            print("  SESSION INITIALIZED SUCCESSFULLY!")
            print("=" * 60)
            print()
            print("  Next steps:")
            print("  1. Start the WhatsApp watcher: pm2 restart whatsapp-watcher")
            print("  2. Check logs: pm2 logs whatsapp-watcher")
            print()
            
            return 0
            
    except KeyboardInterrupt:
        print()
        print("  Session initialization cancelled.")
        return 1
    except Exception as e:
        print()
        print(f"  Error: {e}")
        print()
        print("  Make sure Playwright browsers are installed:")
        print("    playwright install chromium")
        return 1


if __name__ == "__main__":
    sys.exit(main())
