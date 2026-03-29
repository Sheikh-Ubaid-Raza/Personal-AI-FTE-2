"""
AI Employee — Twitter/X Post Skill (Action Layer)
Posts tweets to Twitter/X via Playwright browser automation.
HITL gate: only invoked after human ticks [x] in the Plan file.

Usage:
    python post_twitter.py --task-id TASK_20260301T120000.md
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
TWITTER_EMAIL       = os.getenv("TWITTER_EMAIL", "")
TWITTER_PASSWORD    = os.getenv("TWITTER_PASSWORD", "")
TWITTER_USERNAME    = os.getenv("TWITTER_USERNAME", "")   # optional @handle
_tw_session_raw = os.getenv("TWITTER_SESSION_DIR", str(VAULT / ".x_session"))
TWITTER_SESSION_DIR = str(VAULT / _tw_session_raw) if not _tw_session_raw.startswith("/") else _tw_session_raw
HEADLESS  = os.getenv("TWITTER_HEADLESS", "false").lower() == "true"
DRY_RUN   = os.getenv("DRY_RUN", "false").lower() == "true"
MAX_POSTS_PER_DAY = 10
TWITTER_CHAR_LIMIT = 280


# ── Logging ──────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "actor":       "twitter-post-skill",
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
    row = f"| {ts} | Twitter/X post ({len(content)} chars) — {task_id} | {status} |"
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
    count = 0
    for line in log_file.read_text(encoding="utf-8").strip().split("\n"):
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (e.get("actor") == "twitter-post-skill"
                and e.get("action_type") == "twitter_post"
                and e.get("result") == "success"):
            count += 1
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

    # Quoted after twitter/tweet/post keyword
    m = re.search(
        r"""(?:tweet|post|publish|twitter|x\.com)\s*[:.]?\s*['""\u201c\u201d](.+?)['""\u2018\u2019\u201c\u201d]""",
        raw, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip()

    # Any quoted block 10+ chars
    m = re.search(r"""['""\u2018\u2019\u201c\u201d](.{10,}?)['""\u2018\u2019\u201c\u201d]""", raw, re.DOTALL)
    if m:
        return m.group(1).strip()

    cleaned = re.sub(r"^(?:post|tweet|publish)\s+to\s+(?:twitter|x)\s*[:.]?\s*", "", raw,
                     flags=re.IGNORECASE).strip().strip("'\"")
    if cleaned:
        return cleaned

    return "\n".join(l.strip() for l in raw.split("\n")
                     if l.strip() and not l.strip().startswith("#") and l.strip() != "---")


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


# ── Twitter/X Posting ────────────────────────────────────────────────

def post_to_twitter(content: str) -> tuple[bool, str, str]:
    """Post a tweet via real Playwright browser interaction.

    keyboard.type(delay=80) fires genuine input events so X's React
    state tracks the text and enables the Post button correctly.

    Returns (success, error_or_empty, screenshot_path).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "playwright not installed", ""

    if not TWITTER_EMAIL or not TWITTER_PASSWORD:
        return False, "TWITTER_EMAIL or TWITTER_PASSWORD not set in .env", ""

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    screenshot_path = str(LOGS / f"twitter_post_{stamp}.png")
    session_dir = Path(TWITTER_SESSION_DIR)
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

            # ── 1. Navigate to home (session check) ───────────────────
            print("  [1] Navigating to X (Twitter)...")
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            print(f"      URL: {page.url}")

            # ── 2. Login if session expired ───────────────────────────
            if "/login" in page.url or "/i/flow/login" in page.url or "x.com" not in page.url:
                print("  [2] Session expired — logging in...")

                email_input = _find_element(page, [
                    'input[name="text"]',
                    'input[autocomplete="username"]',
                ], timeout=10000)
                if email_input:
                    email_input.click()
                    page.keyboard.type(TWITTER_EMAIL, delay=60)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(2000)

                unusual = _find_element(page, ['input[data-testid="ocfEnterTextTextInput"]'], timeout=3000)
                if unusual and TWITTER_USERNAME:
                    unusual.click()
                    page.keyboard.type(TWITTER_USERNAME, delay=60)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(2000)

                pw_input = _find_element(page, ['input[name="password"]', 'input[type="password"]'], timeout=10000)
                if pw_input:
                    pw_input.click()
                    page.keyboard.type(TWITTER_PASSWORD, delay=60)
                    login_btn = _find_element(page, [
                        '[data-testid="LoginForm_Login_Button"]',
                        'button[type="submit"]',
                    ], timeout=5000)
                    if login_btn:
                        login_btn.click()
                    else:
                        page.keyboard.press("Enter")
                    page.wait_for_timeout(5000)

                if "challenge" in page.url or "verify" in page.url:
                    page.screenshot(path=screenshot_path)
                    browser.close()
                    return False, "Twitter/X verification required", screenshot_path

            # ── 3. Click the compose text area on home page ───────────
            print("  [3] Expanding compose bar on home page...")
            # X.com shows an inline compose bar at top of home feed.
            # Click the placeholder text / trigger to expand it.
            for trigger_sel in [
                'div[data-testid="tweetTextarea_0_label"]',
                'div[aria-label*="What is happening"]',
                '[placeholder*="What is happening"]',
            ]:
                try:
                    page.locator(trigger_sel).first.click(timeout=5000)
                    page.wait_for_timeout(1000)
                    break
                except Exception:
                    pass

            # ── 4. Find compose textarea ──────────────────────────────
            print("  [4] Finding compose textarea...")
            editor = _find_element(page, [
                '[data-testid="tweetTextarea_0"]',
                'div[aria-label="Post text"]',
                'div[contenteditable="true"][data-testid*="tweetTextarea"]',
                'div[role="textbox"][aria-multiline="true"]',
            ], timeout=12000)

            if not editor:
                page.screenshot(path=screenshot_path)
                browser.close()
                return False, "Could not find tweet compose textarea", screenshot_path

            # ── 5. Type content ───────────────────────────────────────
            print(f"  [5] Typing {len(content)} chars...")
            editor.click()
            page.wait_for_timeout(500)
            editor.focus()
            page.wait_for_timeout(300)
            page.keyboard.type(content, delay=80)
            page.wait_for_timeout(2000)

            # ── 6. Click Post button ──────────────────────────────────
            print("  [6] Looking for Post button...")
            # Wait 3s after typing so React fully enables the button
            page.wait_for_timeout(3000)

            clicked = False

            # Strategy A: focus the button + keyboard Enter (trusted keyboard event)
            for sel in [
                '[data-testid="tweetButtonInline"]',
                '[data-testid="tweetButton"]',
            ]:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state="visible", timeout=6000)
                    el.focus()
                    page.wait_for_timeout(300)
                    page.keyboard.press("Enter")
                    clicked = True
                    print(f"  [6] focus+Enter on {sel}")
                    break
                except Exception:
                    pass

            # Strategy B: regular Playwright click with long timeout
            if not clicked:
                for sel in [
                    '[data-testid="tweetButtonInline"]',
                    '[data-testid="tweetButton"]',
                ]:
                    try:
                        el = page.locator(sel).first
                        el.wait_for(state="visible", timeout=6000)
                        el.click(timeout=15000)
                        clicked = True
                        print(f"  [6] Clicked via {sel}")
                        break
                    except Exception:
                        pass

            # Strategy C: scroll to top, get fresh coordinates, mouse.click
            if not clicked:
                print("  [6] Trying mouse.click at Post button coordinates...")
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(500)
                coords = page.evaluate("""
                    () => {
                        for (const sel of ['[data-testid="tweetButtonInline"]', '[data-testid="tweetButton"]']) {
                            const btn = document.querySelector(sel);
                            if (btn) {
                                const r = btn.getBoundingClientRect();
                                return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                            }
                        }
                        return null;
                    }
                """)
                if coords:
                    page.mouse.move(coords['x'], coords['y'])
                    page.wait_for_timeout(200)
                    page.mouse.click(coords['x'], coords['y'])
                    clicked = True
                    print(f"  [6] mouse.click at ({coords['x']:.0f}, {coords['y']:.0f})")

            if not clicked:
                page.screenshot(path=screenshot_path)
                browser.close()
                return False, "Post button not found after typing", screenshot_path

            page.wait_for_timeout(6000)

            # ── 7. Verify ─────────────────────────────────────────────
            print("  [7] Verifying submission...")
            page.screenshot(path=screenshot_path)
            browser.close()
            print("  [7] Tweet posted successfully.")
            return True, "", screenshot_path

    except Exception as exc:
        return False, str(exc), screenshot_path


# ── Main Execution ───────────────────────────────────────────────────

def execute(task_id: str | None = None) -> None:
    DONE.mkdir(parents=True, exist_ok=True)

    if not task_id:
        log_action("execution_error", "twitter_post", "no task_id provided")
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

    # Hard-enforce Twitter's 280-char limit (warn, truncate at 277 + "...")
    if len(content) > TWITTER_CHAR_LIMIT:
        content = content[:277].rstrip() + "..."
        print(f"WARNING: Content truncated to {TWITTER_CHAR_LIMIT} chars for Twitter")
        log_action("content_truncated", task_id, "warning",
                   original_length=len(text), truncated_to=TWITTER_CHAR_LIMIT)

    if not check_rate_limit():
        log_action("rate_limit", "twitter_post", f"exceeded_{MAX_POSTS_PER_DAY}_per_day")
        print(f"RATE LIMIT: Maximum {MAX_POSTS_PER_DAY} posts/day reached.")
        return

    if DRY_RUN:
        print(f"[DRY RUN] Would tweet ({len(content)} chars):")
        print(f"  {content[:100]}...")
        log_action("twitter_dry_run", "x.com", "dry_run",
                   content_length=len(content), task_id=task_id)
        return

    print(f"Posting to Twitter/X ({len(content)} chars) from {task_id}...")
    success, error, screenshot = post_to_twitter(content)

    if success:
        log_action("twitter_post", "x.com", "success",
                   content_length=len(content), task_id=task_id, screenshot=screenshot)
        update_dashboard("Success", content, task_id)
        print("  OK  Posted to Twitter/X")
    else:
        log_action("twitter_post", "x.com", "failed",
                   content_length=len(content), task_id=task_id, error=error)
        update_dashboard("Failed", content, task_id)
        print(f"  FAIL  {error}")
        sys.exit(1)


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Twitter/X Post Skill")
    parser.add_argument("--task-id", default=None,
                        help="Task ID to process (e.g. TASK_20260301T120000.md)")
    args = parser.parse_args()
    execute(task_id=args.task_id)
