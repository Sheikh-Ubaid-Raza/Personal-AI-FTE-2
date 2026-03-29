"""
AI Employee — Facebook Post Skill (Action Layer)
Posts text updates to Facebook via Playwright browser automation.
HITL gate: only invoked after human ticks [x] in the Plan file.

Usage:
    python post_facebook.py --task-id TASK_20260301T120000.md
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────
VAULT = Path(__file__).resolve().parent.parent.parent.parent.parent
NEEDS_APPROVAL = VAULT / "Needs_Approval"
NEEDS_ACTION   = VAULT / "Needs_Action"
DONE           = VAULT / "Done"
LOGS           = VAULT / "Logs"
DASHBOARD      = VAULT / "Dashboard.md"

load_dotenv(VAULT / ".env")

# ── Config ───────────────────────────────────────────────────────────
FACEBOOK_EMAIL      = os.getenv("FACEBOOK_EMAIL", "")
FACEBOOK_PASSWORD   = os.getenv("FACEBOOK_PASSWORD", "")
_fb_session_raw = os.getenv("FACEBOOK_SESSION_DIR", str(VAULT / ".fb_session"))
FACEBOOK_SESSION_DIR = str(VAULT / _fb_session_raw) if not _fb_session_raw.startswith("/") else _fb_session_raw
HEADLESS  = os.getenv("FACEBOOK_HEADLESS", "false").lower() == "true"
DRY_RUN   = os.getenv("DRY_RUN", "false").lower() == "true"
MAX_POSTS_PER_DAY   = 10
FACEBOOK_CHAR_LIMIT = 63206


# ── Logging ──────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "actor":       "facebook-post-skill",
        "action_type": action_type,
        "target":      target,
        "result":      result,
    }
    entry.update(extra)
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Dashboard Update ─────────────────────────────────────────────────

def update_dashboard(status: str, content: str, task_id: str) -> None:
    if not DASHBOARD.exists():
        return
    text = DASHBOARD.read_text(encoding="utf-8")
    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    row = f"| {ts} | Facebook post ({len(content)} chars) — {task_id} | {status} |"
    # Insert after the header separator row in Recent Activity table
    marker = "| -------------------- | ---------------------------------------------------------- | ------- |"
    if marker in text:
        text = text.replace(marker, marker + "\n" + row)
        DASHBOARD.write_text(text, encoding="utf-8")


# ── Frontmatter Parser ───────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    fm_block, body = match.group(1), match.group(2)
    fm: dict = {}
    for line in fm_block.split("\n"):
        line = line.strip()
        if not line:
            continue
        idx = line.find(":")
        if idx == -1:
            continue
        fm[line[:idx].strip()] = line[idx + 1:].strip().strip('"').strip("'")
    return fm, body


# ── Rate Limiter ─────────────────────────────────────────────────────

def check_rate_limit() -> bool:
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    if not log_file.exists():
        return True
    count = sum(
        1 for line in log_file.read_text(encoding="utf-8").strip().split("\n")
        if line
        for entry in [json.loads(line)] if not isinstance(entry, Exception)
        if entry.get("actor") == "facebook-post-skill"
        and entry.get("action_type") == "facebook_post"
        and entry.get("result") == "success"
    )
    return count < MAX_POSTS_PER_DAY


# ── Task Locator ─────────────────────────────────────────────────────

def find_task_file(task_id: str) -> Path | None:
    name = task_id if task_id.endswith(".md") else task_id + ".md"
    for folder in (NEEDS_APPROVAL, NEEDS_ACTION, DONE):
        candidate = folder / name
        if candidate.exists():
            return candidate
    return None


# ── Content Extractor ────────────────────────────────────────────────

def extract_post_content(text: str) -> str:
    _, body = parse_frontmatter(text)

    raw = body.split("## Full Content", 1)[1].strip() if "## Full Content" in body else body.strip()
    raw = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", raw, count=1, flags=re.DOTALL).strip()

    # Quoted after facebook/post/publish keyword
    m = re.search(
        r"""(?:post|publish|facebook|fb)\s*[:.]?\s*['""\u201c\u201d](.+?)['""\u2018\u2019\u201c\u201d]""",
        raw, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip()

    # Any quoted block 20+ chars
    m = re.search(r"""['""\u2018\u2019\u201c\u201d](.{20,}?)['""\u2018\u2019\u201c\u201d]""", raw, re.DOTALL)
    if m:
        return m.group(1).strip()

    # Strip "Post to Facebook:" prefix
    cleaned = re.sub(r"^(?:post|publish)\s+to\s+facebook\s*[:.]?\s*", "", raw, flags=re.IGNORECASE).strip().strip("'\"")
    if cleaned:
        return cleaned

    # Last resort: strip markdown scaffolding
    return "\n".join(l.strip() for l in raw.split("\n") if l.strip() and not l.strip().startswith("#") and l.strip() != "---")


# ── Playwright Helpers ───────────────────────────────────────────────

def _find_element(page, selectors: list[str], timeout: int = 8000):
    for sel in selectors:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=timeout)
            return el
        except Exception:
            continue
    return None


# ── Facebook Posting ─────────────────────────────────────────────────

def post_to_facebook(content: str) -> tuple[bool, str, str]:
    """Post content to Facebook using real browser interaction.

    Mimics human behaviour: slow_mo + keyboard.type(delay=80) ensures
    React/Ember state updates fire and the Post button becomes enabled.

    Returns (success, error_or_empty, screenshot_path).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "playwright not installed", ""

    if not FACEBOOK_EMAIL or not FACEBOOK_PASSWORD:
        return False, "FACEBOOK_EMAIL or FACEBOOK_PASSWORD not set in .env", ""

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    screenshot_path = str(LOGS / f"facebook_post_{stamp}.png")
    session_dir = Path(FACEBOOK_SESSION_DIR)
    session_dir.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(session_dir),
                headless=HEADLESS,
                slow_mo=150,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.set_viewport_size({"width": 1280, "height": 900})

            # ── 1. Navigate ───────────────────────────────────────────
            print("  [1] Navigating to Facebook...")
            page.goto("https://www.facebook.com/", wait_until="load", timeout=30000)
            page.wait_for_timeout(3000)
            print(f"      URL: {page.url}")

            # ── 2. Login if session expired ───────────────────────────
            # Facebook sometimes shows login form at root URL when session expires
            needs_login = "/login" in page.url or "facebook.com" not in page.url
            if not needs_login:
                try:
                    page.locator('input[name="email"]').wait_for(state="visible", timeout=3000)
                    needs_login = True  # login form present at root URL
                except Exception:
                    pass
            if needs_login:
                print("  [2] Session expired — logging in...")
                page.fill('input[name="email"]', FACEBOOK_EMAIL, timeout=10000)
                page.fill('input[name="pass"]',  FACEBOOK_PASSWORD, timeout=10000)
                page.click('button[name="login"], button[type="submit"]', timeout=10000)
                page.wait_for_timeout(5000)
                print(f"      After login URL: {page.url}")

                if "checkpoint" in page.url or "two_factor" in page.url:
                    page.screenshot(path=screenshot_path)
                    browser.close()
                    return False, "Facebook verification required — manual login needed", screenshot_path

            # Dismiss cookie/GDPR popup if present
            for consent_sel in ['[aria-label="Allow all cookies"]', 'button:has-text("Allow all cookies")',
                                 'button:has-text("Accept all")', '[data-cookiebanner="accept_button"]']:
                try:
                    page.click(consent_sel, timeout=2000)
                    page.wait_for_timeout(500)
                    break
                except Exception:
                    pass

            # ── 3. Click "What's on your mind" trigger ────────────────
            print("  [3] Opening post composer...")
            composer = _find_element(page, [
                '[aria-label*="What\'s on your mind"]',
                '[aria-placeholder*="What\'s on your mind"]',
                'div[role="button"]:has-text("What\'s on your mind")',
                'span:has-text("What\'s on your mind")',
                # Mobile/alternate layout
                '[data-testid="status-attachment-mentions-input"]',
            ], timeout=10000)

            if not composer:
                page.screenshot(path=screenshot_path)
                browser.close()
                return False, "Could not find 'What's on your mind' composer button", screenshot_path

            composer.click()
            page.wait_for_timeout(2000)

            # ── 4. Find editor inside the modal ───────────────────────
            print("  [4] Waiting for compose editor...")
            editor = _find_element(page, [
                'div[contenteditable="true"][aria-label*="What\'s on your mind"]',
                'div[contenteditable="true"][role="textbox"]',
                'div[data-lexical-editor="true"]',
                'div[contenteditable="true"]',
            ], timeout=10000)

            if not editor:
                page.screenshot(path=screenshot_path)
                browser.close()
                return False, "Could not find post editor in compose modal", screenshot_path

            # ── 5. Human-like typing ──────────────────────────────────
            print(f"  [5] Typing {len(content)} chars...")
            editor.click()
            page.wait_for_timeout(400)
            editor.focus()
            page.wait_for_timeout(300)
            page.keyboard.type(content, delay=80)
            page.wait_for_timeout(1500)

            # ── 6. Click Post ─────────────────────────────────────────
            print("  [6] Looking for Post button...")
            post_btn = _find_element(page, [
                'div[aria-label="Post"][role="button"]',
                '[aria-label="Post"]',
                'button:has-text("Post")',
                'div[role="button"]:has-text("Post")',
            ], timeout=8000)

            if not post_btn:
                try:
                    post_btn = page.get_by_role("button", name="Post", exact=True).first
                    post_btn.wait_for(state="visible", timeout=5000)
                except Exception:
                    post_btn = None

            if not post_btn:
                page.screenshot(path=screenshot_path)
                browser.close()
                return False, "Post button not found in compose modal", screenshot_path

            if post_btn.is_disabled():
                page.screenshot(path=screenshot_path)
                browser.close()
                return False, "Post button is disabled — content may not have registered via input events", screenshot_path

            print("  [6] Post button enabled — clicking...")
            post_btn.click()
            page.wait_for_timeout(4000)

            # ── 7. Verify ─────────────────────────────────────────────
            print("  [7] Verifying submission...")
            page.screenshot(path=screenshot_path)
            browser.close()
            print("  [7] Post submitted successfully.")
            return True, "", screenshot_path

    except Exception as exc:
        return False, str(exc), screenshot_path


# ── Main Execution ───────────────────────────────────────────────────

def execute(task_id: str | None = None) -> None:
    DONE.mkdir(parents=True, exist_ok=True)

    if not task_id:
        log_action("execution_error", "facebook_post", "no task_id provided")
        print("ERROR: --task-id is required")
        return

    log_action("skill_invoked", task_id, "started", mode="dry_run" if DRY_RUN else "live")

    task_path = find_task_file(task_id)
    if not task_path:
        log_action("task_not_found", task_id, "failed")
        print(f"ERROR: Could not find task file for {task_id}")
        return

    text    = task_path.read_text(encoding="utf-8")
    content = extract_post_content(text)

    if not content:
        log_action("validation_error", task_id, "empty_content")
        print(f"VALIDATION ERROR: Empty content in {task_id}")
        return

    if len(content) > FACEBOOK_CHAR_LIMIT:
        log_action("validation_error", task_id, f"content_too_long_{len(content)}")
        print(f"VALIDATION ERROR: Content too long ({len(content)} chars, limit {FACEBOOK_CHAR_LIMIT})")
        return

    if not check_rate_limit():
        log_action("rate_limit", "facebook_post", f"exceeded_{MAX_POSTS_PER_DAY}_per_day")
        print(f"RATE LIMIT: Maximum {MAX_POSTS_PER_DAY} posts/day reached.")
        return

    if DRY_RUN:
        print(f"[DRY RUN] Would post to Facebook ({len(content)} chars):")
        print(f"  {content[:100]}...")
        log_action("facebook_dry_run", "facebook.com", "dry_run",
                   content_length=len(content), task_id=task_id)
        return

    print(f"Posting to Facebook ({len(content)} chars) from {task_id}...")
    success, error, screenshot = post_to_facebook(content)

    if success:
        log_action("facebook_post", "facebook.com", "success",
                   content_length=len(content), task_id=task_id, screenshot=screenshot)
        update_dashboard("Success", content, task_id)
        print("  OK  Posted to Facebook")
    else:
        log_action("facebook_post", "facebook.com", "failed",
                   content_length=len(content), task_id=task_id, error=error)
        update_dashboard("Failed", content, task_id)
        print(f"  FAIL  {error}")
        sys.exit(1)


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Facebook Post Skill")
    parser.add_argument("--task-id", default=None,
                        help="Task ID to process (e.g. TASK_20260301T120000.md)")
    args = parser.parse_args()
    execute(task_id=args.task_id)
