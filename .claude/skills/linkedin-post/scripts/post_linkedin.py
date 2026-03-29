"""
AI Employee — LinkedIn Post Skill (Action Layer)
Publishes text posts to LinkedIn via Playwright browser automation.
Authorization is handled by the Orchestrator's Checkbox Approval gate —
if this script is invoked, the human has already ticked [x] in the plan.

Usage:
    python post_linkedin.py --task-id TASK_20260215T090000.md
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
NEEDS_ACTION = VAULT / "Needs_Action"
DONE = VAULT / "Done"
LOGS = VAULT / "Logs"

load_dotenv(VAULT / ".env")

# ── Config ───────────────────────────────────────────────────────────
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")
_li_session_raw = os.getenv("LINKEDIN_SESSION_DIR", str(VAULT / ".linkedin_session"))
LINKEDIN_SESSION_DIR = str(VAULT / _li_session_raw) if not _li_session_raw.startswith("/") else _li_session_raw
HEADLESS = os.getenv("LINKEDIN_HEADLESS", "true").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
MAX_POSTS_PER_DAY = 10
LINKEDIN_CHAR_LIMIT = 3000


# ── Logging ──────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    """Append a JSON audit entry to today's log file."""
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": "linkedin-post-skill",
        "action_type": action_type,
        "target": target,
        "result": result,
    }
    entry.update(extra)
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Frontmatter Parser ───────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter. Returns (dict, body)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    fm_block, body = match.group(1), match.group(2)
    fm = {}
    for line in fm_block.split("\n"):
        line = line.strip()
        if not line:
            continue
        colon_idx = line.find(":")
        if colon_idx == -1:
            continue
        key = line[:colon_idx].strip()
        value = line[colon_idx + 1:].strip().strip('"').strip("'")
        fm[key] = value
    return fm, body


# ── Rate Limiter ─────────────────────────────────────────────────────

def check_rate_limit() -> bool:
    """Return True if under the daily post limit."""
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    if not log_file.exists():
        return True
    count = 0
    for line in log_file.read_text(encoding="utf-8").strip().split("\n"):
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (entry.get("actor") == "linkedin-post-skill"
                and entry.get("action_type") == "linkedin_post"
                and entry.get("result") == "success"):
            count += 1
    return count < MAX_POSTS_PER_DAY


# ── Task File Locator ───────────────────────────────────────────────

def find_task_file(task_id: str) -> Path | None:
    """Locate a TASK file across vault directories."""
    name = task_id if task_id.endswith(".md") else task_id + ".md"
    for folder in (NEEDS_APPROVAL, NEEDS_ACTION, DONE):
        candidate = folder / name
        if candidate.exists():
            return candidate
    return None


# ── Post Content Extractor ───────────────────────────────────────────

def extract_post_content(text: str) -> str:
    """Extract LinkedIn post content from task body.

    Priority order:
    1. Text inside quotes after a "post"/"linkedin"/"publish" keyword
    2. Text inside any quotes (20+ chars)
    3. Raw text from the "## Full Content" section (header-stripped)
    4. Raw text from the full body (header-stripped)
    """
    _, body = parse_frontmatter(text)

    # Prefer the "## Full Content" section — most reliable source
    if "## Full Content" in body:
        raw_section = body.split("## Full Content", 1)[1].strip()
    else:
        raw_section = body.strip()

    # Strip any embedded YAML frontmatter block at the start of raw_section
    # (created when the watcher wraps Inbox files that have their own frontmatter)
    raw_section = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", raw_section,
                         count=1, flags=re.DOTALL).strip()

    # 1. Quoted content after post/linkedin/publish keyword
    m = re.search(
        r"""(?:post|publish|linkedin)\s*[:.]\s*['"\u2018\u2019\u201c\u201d](.+?)['"\u2018\u2019\u201c\u201d]""",
        raw_section, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip()

    # 2. Any quoted block 20+ chars
    m = re.search(
        r"""['"\u2018\u2019\u201c\u201d](.{20,}?)['"\u2018\u2019\u201c\u201d]""",
        raw_section, re.DOTALL,
    )
    if m:
        return m.group(1).strip()

    # 3. Strip "Post to LinkedIn:" prefix if present, then return clean text
    cleaned = re.sub(
        r"^(?:post|publish)\s+to\s+linkedin\s*[:.]?\s*", "",
        raw_section, flags=re.IGNORECASE,
    ).strip().strip("'\"")
    if cleaned:
        return cleaned

    # 4. Last resort: strip markdown scaffolding
    lines = []
    for line in raw_section.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped != "---":
            lines.append(stripped)
    return "\n".join(lines)


# ── LinkedIn Posting via Playwright UI ───────────────────────────────
# Strategy: real browser interaction with human-like typing.
# Key fix: editor.focus() + page.keyboard.type(delay=80) fires genuine
# "input" events that Ember.js/React track — making the Post button
# become enabled reliably.  We skip the audience-settings sub-modal
# entirely (post to default "Anyone") to eliminate the Done-button issue.

def _find_and_click(page, selectors: list[str], timeout: int = 5000) -> bool:
    """Try each selector in order; click the first visible match. Returns True on success."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=timeout)
            el.click()
            return True
        except Exception:
            continue
    return False


def _find_element(page, selectors: list[str], timeout: int = 8000):
    """Return the first visible element matching any selector, or None."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=timeout)
            return el
        except Exception:
            continue
    return None


def post_to_linkedin(content: str) -> tuple[bool, str, str]:
    """Post content to LinkedIn via real Playwright browser interaction.

    Uses human-like typing (keyboard.type with delay) so that Ember.js /
    React state updates fire correctly and the Post button becomes enabled.
    The audience-settings modal is intentionally skipped — posts go to
    the default "Anyone" audience, which avoids the unreliable Done button.

    Returns (success, error_or_empty, screenshot_path).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "playwright not installed", ""

    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        return False, "LINKEDIN_EMAIL or LINKEDIN_PASSWORD not set in .env", ""

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    screenshot_path = str(LOGS / f"linkedin_post_{stamp}.png")
    session_dir = Path(LINKEDIN_SESSION_DIR)
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
                    "--disable-dev-shm-usage",   # prevents Chromium crash in WSL2
                    "--disable-gpu",
                ],
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.set_viewport_size({"width": 1280, "height": 900})

            # ── 1. Navigate to LinkedIn feed ──────────────────────────
            print("  [1] Navigating to LinkedIn feed...")
            page.goto("https://www.linkedin.com/feed/",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            print(f"      URL: {page.url}")

            # ── 2. Login if session has expired ──────────────────────
            if "login" in page.url or "checkpoint" in page.url:
                print("  [2] Session expired — logging in...")
                page.fill('input[name="session_key"]', LINKEDIN_EMAIL, timeout=10000)
                page.fill('input[name="session_password"]', LINKEDIN_PASSWORD, timeout=10000)
                page.click('button[type="submit"]', timeout=10000)
                page.wait_for_timeout(5000)
                print(f"      After login URL: {page.url}")

                if "checkpoint" in page.url or "challenge" in page.url:
                    page.screenshot(path=screenshot_path)
                    browser.close()
                    return (False,
                            "LinkedIn verification challenge — manual login required",
                            screenshot_path)

            # ── 3. Click "Start a post" trigger ──────────────────────
            print("  [3] Clicking 'Start a post'...")
            clicked = _find_and_click(page, [
                # Modern LinkedIn class (2024-2025)
                "button.share-box-feed-entry__trigger",
                # Text-based fallbacks
                'button:has-text("Start a post")',
                '[placeholder*="Start a post"]',
                # Aria-label fallback
                '[aria-label*="Start a post"]',
                # Generic trigger div
                '.share-box-feed-entry__top-bar',
            ], timeout=8000)

            if not clicked:
                # Last resort: click by visible text
                try:
                    page.get_by_text("Start a post", exact=False).first.click()
                    clicked = True
                except Exception:
                    pass

            if not clicked:
                page.screenshot(path=screenshot_path)
                browser.close()
                return False, "Could not find 'Start a post' button on feed", screenshot_path

            page.wait_for_timeout(2000)

            # ── 4. Find the rich-text editor in the compose modal ─────
            print("  [4] Waiting for compose editor...")
            editor = _find_element(page, [
                # Quill editor (most common in LinkedIn compose)
                "div.ql-editor",
                # Generic contenteditable inside the modal
                '.share-creation-state__editor [contenteditable="true"]',
                # Broad fallback — any visible contenteditable
                '[contenteditable="true"]',
            ], timeout=10000)

            if not editor:
                page.screenshot(path=screenshot_path)
                browser.close()
                return False, "Compose editor not found after clicking 'Start a post'", screenshot_path

            # ── 5. Focus → human-like typing → fires real input events ─
            print(f"  [5] Typing {len(content)} chars into editor...")
            editor.click()
            page.wait_for_timeout(400)
            editor.focus()
            page.wait_for_timeout(300)
            # keyboard.type fires keydown/keypress/input/keyup for each char
            page.keyboard.type(content, delay=80)
            page.wait_for_timeout(1500)

            # ── 6. Find and click the "Post" button ───────────────────
            print("  [6] Looking for Post button...")
            post_btn = _find_element(page, [
                # Primary action button in share dialog
                "button.share-actions__primary-action",
                "button[data-control-name='share.post']",
                # Text / role fallbacks
                'button:has-text("Post")',
                '[aria-label="Post"]',
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

            # Confirm the button is enabled before clicking
            if post_btn.is_disabled():
                page.screenshot(path=screenshot_path)
                browser.close()
                return (False,
                        "Post button is still disabled — editor may not have received input events",
                        screenshot_path)

            print("  [6] Post button is enabled — clicking...")
            post_btn.click()
            page.wait_for_timeout(4000)

            # ── 7. Verify success: compose modal should be gone ───────
            print("  [7] Verifying post was submitted...")
            modal_gone = True
            try:
                page.locator(
                    ".share-creation-state, .share-box-v2, div.ql-editor"
                ).first.wait_for(state="visible", timeout=2000)
                modal_gone = False          # still visible → something went wrong
            except Exception:
                modal_gone = True           # timed out ≈ modal closed ✓

            page.screenshot(path=screenshot_path)
            browser.close()

            if not modal_gone:
                return (False,
                        "Compose modal still open after clicking Post — check screenshot",
                        screenshot_path)

            print("  [7] Modal closed — post submitted successfully.")
            return True, "", screenshot_path

    except Exception as exc:
        return False, str(exc), screenshot_path


# ── Main Execution ───────────────────────────────────────────────────

def execute(task_id: str | None = None) -> None:
    """Run the linkedin-post skill.

    Authorization is handled upstream by the Orchestrator's Checkbox
    Approval gate.  This script trusts that if it is invoked, the
    human has already approved the action.
    """
    DONE.mkdir(parents=True, exist_ok=True)

    if not task_id:
        log_action("execution_error", "linkedin_post", "no task_id provided")
        print("ERROR: --task-id is required")
        return

    log_action("skill_invoked", task_id, "started",
               mode="dry_run" if DRY_RUN else "live")

    # ── Locate task file ─────────────────────────────────────────────
    task_path = find_task_file(task_id)
    if not task_path:
        log_action("task_not_found", task_id, "failed")
        print(f"ERROR: Could not find task file for {task_id}")
        return

    text = task_path.read_text(encoding="utf-8")

    # ── Extract post content ─────────────────────────────────────────
    content = extract_post_content(text)

    # ── Validate ─────────────────────────────────────────────────────
    if not content:
        log_action("validation_error", task_id, "Empty post content")
        print(f"VALIDATION ERROR: Empty content in {task_id}")
        return

    if len(content) > LINKEDIN_CHAR_LIMIT:
        log_action("validation_error", task_id,
                   f"Content exceeds {LINKEDIN_CHAR_LIMIT} chars ({len(content)})")
        print(f"VALIDATION ERROR: Content too long ({len(content)} chars)")
        return

    # ── Rate Limit ───────────────────────────────────────────────────
    if not check_rate_limit():
        log_action("rate_limit", "linkedin_post",
                   f"BLOCKED: Exceeded {MAX_POSTS_PER_DAY} posts/day")
        print(f"RATE LIMIT: Maximum {MAX_POSTS_PER_DAY} posts per day reached.")
        return

    now_iso = datetime.now(timezone.utc).isoformat()

    # ── DRY RUN ──────────────────────────────────────────────────────
    if DRY_RUN:
        print(f"[DRY RUN] Would post to LinkedIn ({len(content)} chars):")
        print(f"  {content[:80]}...")
        log_action("linkedin_dry_run", "linkedin.com", "dry_run",
                   content_length=len(content), task_id=task_id)
        return

    # ── Post ─────────────────────────────────────────────────────────
    print(f"Posting to LinkedIn ({len(content)} chars) from {task_id}...")
    success, error, screenshot = post_to_linkedin(content)

    if success:
        log_action("linkedin_post", "linkedin.com", "success",
                   content_length=len(content), task_id=task_id,
                   screenshot=screenshot)
        print(f"  OK  Posted to LinkedIn")
    else:
        log_action("linkedin_post", "linkedin.com", "failed",
                   content_length=len(content), task_id=task_id,
                   error=error)
        print(f"  FAIL  {error}")
        sys.exit(1)


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedIn Post Skill")
    parser.add_argument("--task-id", default=None,
                        help="Task ID to process (e.g. TASK_20260215T090000.md)")
    args = parser.parse_args()
    execute(task_id=args.task_id)
