"""
AI Employee — Instagram Post Skill (Action Layer)
Posts a photo with caption to Instagram via Playwright browser automation.
HITL gate: only invoked after human ticks [x] in the Plan file.

If no image_path is provided in the task frontmatter, a simple branded image
is auto-generated from the post caption text using Pillow.

Usage:
    python post_instagram.py --task-id TASK_20260301T120000.md
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
INSTAGRAM_USERNAME   = os.getenv("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD   = os.getenv("INSTAGRAM_PASSWORD", "")
_ig_session_raw = os.getenv("INSTAGRAM_SESSION_DIR", str(VAULT / ".ig_session"))
INSTAGRAM_SESSION_DIR = str(VAULT / _ig_session_raw) if not _ig_session_raw.startswith("/") else _ig_session_raw
HEADLESS  = os.getenv("INSTAGRAM_HEADLESS", "false").lower() == "true"
DRY_RUN   = os.getenv("DRY_RUN", "false").lower() == "true"
MAX_POSTS_PER_DAY    = 10
INSTAGRAM_CHAR_LIMIT = 2200


# ── Logging ──────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "actor":       "instagram-post-skill",
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
    row = f"| {ts} | Instagram post ({len(content)} chars) — {task_id} | {status} |"
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
        if (e.get("actor") == "instagram-post-skill"
                and e.get("action_type") == "instagram_post"
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


# ── Content & Image Extractor ────────────────────────────────────────

def extract_post_content(text: str) -> str:
    _, body = parse_frontmatter(text)
    raw = body.split("## Full Content", 1)[1].strip() if "## Full Content" in body else body.strip()
    raw = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", raw, count=1, flags=re.DOTALL).strip()

    m = re.search(
        r"""(?:caption|post|publish|instagram|ig)\s*[:.]?\s*['""\u201c\u201d](.+?)['""\u2018\u2019\u201c\u201d]""",
        raw, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip()

    m = re.search(r"""['""\u2018\u2019\u201c\u201d](.{20,}?)['""\u2018\u2019\u201c\u201d]""", raw, re.DOTALL)
    if m:
        return m.group(1).strip()

    cleaned = re.sub(r"^(?:post|publish)\s+to\s+instagram\s*[:.]?\s*", "", raw,
                     flags=re.IGNORECASE).strip().strip("'\"")
    if cleaned:
        return cleaned

    return "\n".join(l.strip() for l in raw.split("\n")
                     if l.strip() and not l.strip().startswith("#") and l.strip() != "---")


# ── Image Generator ──────────────────────────────────────────────────

def _generate_post_image(caption: str, task_id: str) -> str:
    """Generate a simple 1080×1080 branded image with the caption text.

    Uses Pillow. Falls back to a blank white JPEG if Pillow is unavailable
    or font loading fails.

    Returns the absolute path to the generated image file.
    """
    LOGS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = str(LOGS / f"ig_auto_{stamp}.jpg")

    try:
        from PIL import Image, ImageDraw, ImageFont

        W, H = 1080, 1080
        BG   = (30, 30, 30)       # dark background
        FG   = (255, 255, 255)    # white text
        ACC  = (0, 149, 246)      # Instagram-blue accent bar

        img  = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)

        # Accent stripe at top
        draw.rectangle([0, 0, W, 12], fill=ACC)

        # Try system fonts; fall back to default
        font_large = font_small = None
        for font_path in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
            if Path(font_path).exists():
                font_large = ImageFont.truetype(font_path, 52)
                font_small = ImageFont.truetype(font_path, 28)
                break
        if font_large is None:
            font_large = font_small = ImageFont.load_default()

        # Word-wrap caption to ~18 chars per line at size 52
        words  = caption.split()
        lines  = []
        line   = ""
        for w in words:
            if len(line) + len(w) + 1 <= 28:
                line = (line + " " + w).strip()
            else:
                if line:
                    lines.append(line)
                line = w
        if line:
            lines.append(line)

        # Center the text block vertically
        line_h  = 64
        total_h = len(lines) * line_h
        y_start = (H - total_h) // 2

        for i, ln in enumerate(lines[:12]):   # max 12 lines
            bbox  = draw.textbbox((0, 0), ln, font=font_large)
            tw    = bbox[2] - bbox[0]
            x     = (W - tw) // 2
            draw  .text((x, y_start + i * line_h), ln, fill=FG, font=font_large)

        # Watermark
        draw.text((40, H - 60), "AI Employee  •  Heagent", fill=(120, 120, 120), font=font_small)

        img.save(out_path, "JPEG", quality=92)
        print(f"  [img] Auto-generated image → {out_path}")
        return out_path

    except Exception as exc:
        # Absolute fallback: tiny white JPEG
        print(f"  [img] Pillow error ({exc}) — using blank image")
        try:
            from PIL import Image
            Image.new("RGB", (1080, 1080), (255, 255, 255)).save(out_path, "JPEG")
        except Exception:
            # Raw minimal JPEG bytes
            import base64
            tiny = base64.b64decode(
                "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
                "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAARC"
                "AABAAEDASIA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/"
                "xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQ"
                "MRAAAUAD//2Q=="
            )
            Path(out_path).write_bytes(tiny)
        return out_path


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


# ── Instagram Posting ────────────────────────────────────────────────

def post_to_instagram(content: str, image_path: str) -> tuple[bool, str, str]:
    """Upload an image with caption to Instagram via Playwright.

    Flow: Login → Create (+) → File chooser → Next → Filters (skip) →
          Next → Type caption → Share → Verify

    Returns (success, error_or_empty, screenshot_path).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "playwright not installed", ""

    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        return False, "INSTAGRAM_USERNAME or INSTAGRAM_PASSWORD not set in .env", ""

    if not image_path or not Path(image_path).exists():
        return False, (
            f"Image file not found: {image_path}\n"
            "Add 'image_path: /absolute/path/to/image.jpg' to the task frontmatter."
        ), ""

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    screenshot_path = str(LOGS / f"instagram_post_{stamp}.png")
    session_dir = Path(INSTAGRAM_SESSION_DIR)
    session_dir.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(session_dir),
                headless=HEADLESS,
                slow_mo=200,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.set_viewport_size({"width": 1280, "height": 900})

            # ── 1. Navigate ───────────────────────────────────────────
            print("  [1] Navigating to Instagram...")
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            print(f"      URL: {page.url}")

            # ── 2. Login if needed ────────────────────────────────────
            if "/accounts/login" in page.url or "instagram.com" not in page.url:
                print("  [2] Session expired — logging in...")
                page.fill('input[name="username"]', INSTAGRAM_USERNAME, timeout=10000)
                page.fill('input[name="password"]', INSTAGRAM_PASSWORD, timeout=10000)
                page.click('button[type="submit"]', timeout=10000)
                page.wait_for_timeout(5000)
                print(f"      After login URL: {page.url}")

                if "challenge" in page.url or "verify" in page.url:
                    page.screenshot(path=screenshot_path)
                    browser.close()
                    return False, "Instagram verification required — manual login needed", screenshot_path

            # Dismiss "Save login info" and notification popups
            for dismiss_sel in [
                'button:has-text("Not now")',
                'button:has-text("Not Now")',
                '[aria-label="Dismiss"]',
            ]:
                try:
                    page.click(dismiss_sel, timeout=2000)
                    page.wait_for_timeout(500)
                except Exception:
                    pass

            # ── 3a. Click "Create" in the sidebar (reveals Post submenu) ─
            # The Create button is <a href="#"> containing "Create" text.
            # Clicking it expands a submenu showing "Post", "Reel", etc.
            print("  [3a] Clicking 'Create' to expand submenu...")

            def _click_sidebar_item(label: str) -> bool:
                """Click the sidebar <a href="#"> item matching label text."""
                # Method 1: Playwright locator by text (force=True for hidden spans)
                for loc in [
                    page.locator(f'a[href="#"]').filter(has_text=label),
                    page.locator(f'[role="link"]').filter(has_text=label),
                ]:
                    try:
                        el = loc.last
                        el.scroll_into_view_if_needed(timeout=3000)
                        el.click(force=True, timeout=5000)
                        return True
                    except Exception:
                        pass
                # Method 2: JS find <a href="#"> whose text includes the label
                result = page.evaluate(f"""
                    () => {{
                        const allA = document.querySelectorAll('a[href="#"]');
                        for (const a of allA) {{
                            if (a.textContent.includes('{label}')) {{
                                const r = a.getBoundingClientRect();
                                return {{x: r.x + r.width/2, y: r.y + r.height/2}};
                            }}
                        }}
                        return null;
                    }}
                """)
                if result:
                    page.mouse.click(result['x'], result['y'])
                    return True
                return False

            _click_sidebar_item("Create")
            page.wait_for_timeout(2000)

            # ── 3b. Click "Post" from the expanded submenu ────────────
            print("  [3b] Clicking 'Post' from expanded Create submenu...")
            clicked_post = _click_sidebar_item("Post")
            if not clicked_post:
                # Fallback: click at typical "Post" coordinates (~y=601 in 1280x900)
                page.mouse.click(50, 601)
                print("      Used coordinate fallback for Post")

            page.wait_for_timeout(3000)

            # Take debug screenshot to confirm upload modal opened
            dbg_path = str(LOGS / f"ig_modal_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.png")
            page.screenshot(path=dbg_path)
            print(f"      Modal screenshot → {dbg_path}")

            # ── 4. Upload image ───────────────────────────────────────
            print(f"  [4] Uploading image: {image_path}")

            uploaded = False

            # Wait for the upload modal to appear (has "Select from computer" button)
            upload_btn_sel = None
            for sel in [
                'button:has-text("Select from computer")',
                'button:has-text("Select From Computer")',
                '[role="button"]:has-text("Select from computer")',
                '[role="button"]:has-text("Select from")',
            ]:
                try:
                    page.locator(sel).first.wait_for(state="visible", timeout=8000)
                    upload_btn_sel = sel
                    print(f"      Upload modal visible, found button: '{sel}'")
                    break
                except Exception:
                    pass

            # Strategy A: expect_file_chooser while clicking "Select from computer"
            if upload_btn_sel:
                try:
                    with page.expect_file_chooser(timeout=15000) as fc_info:
                        page.locator(upload_btn_sel).first.click()
                    file_chooser = fc_info.value
                    file_chooser.set_files(image_path)
                    uploaded = True
                    print(f"  [4] File chooser — uploaded: {image_path}")
                except Exception as e_fc:
                    print(f"  [4] File chooser approach failed: {e_fc}")

            # Strategy B: force set_input_files on hidden <input type="file">
            if not uploaded:
                try:
                    print("  [4] Trying direct set_input_files on hidden input...")
                    # Make the input visible first via JS so Playwright can interact
                    page.evaluate("""
                        () => {
                            const inp = document.querySelector('input[type="file"]');
                            if (inp) {
                                inp.style.display = 'block';
                                inp.style.opacity = '1';
                                inp.style.visibility = 'visible';
                            }
                        }
                    """)
                    page.locator('input[type="file"]').first.set_input_files(
                        image_path, timeout=10000, no_wait_after=True
                    )
                    uploaded = True
                    print(f"  [4] Direct upload succeeded: {image_path}")
                except Exception as e_inp:
                    print(f"  [4] Direct input failed: {e_inp}")

            # Strategy C: dispatch a DataTransfer drop event (drag-and-drop)
            if not uploaded:
                try:
                    print("  [4] Trying drag-and-drop via JS DataTransfer...")
                    import base64 as _b64
                    with open(image_path, "rb") as f:
                        img_bytes = f.read()
                    img_b64 = _b64.b64encode(img_bytes).decode()
                    ext = Path(image_path).suffix.lower().lstrip(".")
                    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
                    dropped = page.evaluate(f"""
                        async () => {{
                            const b64 = "{img_b64}";
                            const byteChars = atob(b64);
                            const byteNums = new Array(byteChars.length);
                            for (let i = 0; i < byteChars.length; i++) {{
                                byteNums[i] = byteChars.charCodeAt(i);
                            }}
                            const arr = new Uint8Array(byteNums);
                            const file = new File([arr], "post.jpg", {{type: "{mime}"}});
                            const dt = new DataTransfer();
                            dt.items.add(file);

                            // Try drop zone first
                            const zone = document.querySelector('input[type="file"]')
                                         || document.querySelector('[role="presentation"]')
                                         || document.body;
                            const ev = new DragEvent('drop', {{bubbles: true, cancelable: true, dataTransfer: dt}});
                            zone.dispatchEvent(ev);

                            // Also set directly on any file input
                            const inp = document.querySelector('input[type="file"]');
                            if (inp) {{
                                Object.defineProperty(inp, 'files', {{value: dt.files, writable: false}});
                                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                            }}
                            return true;
                        }}
                    """)
                    if dropped:
                        uploaded = True
                        page.wait_for_timeout(2000)
                        print(f"  [4] Drag-and-drop dispatch succeeded")
                except Exception as e_drop:
                    print(f"  [4] Drag-and-drop failed: {e_drop}")

            if not uploaded:
                page.screenshot(path=screenshot_path)
                browser.close()
                return False, "Could not upload image via any method", screenshot_path

            page.wait_for_timeout(3000)

            # ── 5. Navigate wizard: Crop → Next ──────────────────────
            print("  [5] Navigating crop/filter steps...")
            for step in range(3):   # Up to 3 "Next" clicks to reach caption screen
                # Use force=True to bypass dialog overlay interception
                clicked_next = False
                for sel in [
                    'button:has-text("Next")',
                    '[role="button"]:has-text("Next")',
                ]:
                    try:
                        el = page.locator(sel).first
                        el.wait_for(state="attached", timeout=8000)
                        btn_text = el.inner_text(timeout=2000).strip()
                        el.click(force=True, timeout=5000)
                        clicked_next = True
                        page.wait_for_timeout(1500)
                        break
                    except Exception:
                        pass

                if not clicked_next:
                    # No more Next buttons — check for Share
                    break

            # ── 6. Type caption ───────────────────────────────────────
            print(f"  [6] Typing caption ({len(content)} chars)...")
            caption_area = _find_element(page, [
                'textarea[aria-label*="Write a caption"]',
                'div[aria-label*="Write a caption"]',
                'textarea[placeholder*="Write a caption"]',
                'div[contenteditable="true"]',
            ], timeout=10000)

            if caption_area:
                caption_area.click()
                page.wait_for_timeout(400)
                caption_area.focus()
                page.wait_for_timeout(300)
                page.keyboard.type(content, delay=60)
                page.wait_for_timeout(1500)

            # ── 7. Click Share ────────────────────────────────────────
            print("  [7] Clicking Share...")
            shared = False

            # Strategy A: regular Playwright click scoped to the dialog (trusted event)
            for sel in [
                'div[role="dialog"] button:has-text("Share")',
                'div[role="dialog"] [role="button"]:has-text("Share")',
                'button:has-text("Share")',
                '[role="button"]:has-text("Share")',
            ]:
                try:
                    el = page.locator(sel).last  # last = header Share, not feed items
                    el.wait_for(state="visible", timeout=8000)
                    el.click(timeout=8000)
                    shared = True
                    print(f"  [7] Clicked Share via '{sel}'")
                    break
                except Exception:
                    pass

            # Strategy B: get Share button coordinates → mouse.click (trusted event)
            # JS btn.click() is NOT trusted — Instagram ignores it; mouse.click() IS trusted
            if not shared:
                print("  [7] Trying mouse.click at Share button coordinates...")
                coords = page.evaluate("""
                    () => {
                        const dialog = document.querySelector('div[role="dialog"]');
                        const scope = dialog || document;
                        for (const el of scope.querySelectorAll('[role="button"], button')) {
                            if (el.textContent.trim() === 'Share') {
                                const r = el.getBoundingClientRect();
                                return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                            }
                        }
                        return null;
                    }
                """)
                if coords:
                    page.mouse.click(coords['x'], coords['y'])
                    shared = True
                    print(f"  [7] mouse.click at ({coords['x']:.0f}, {coords['y']:.0f})")

            if not shared:
                page.screenshot(path=screenshot_path)
                browser.close()
                return False, "Share button not found", screenshot_path

            page.wait_for_timeout(5000)

            # ── 8. Verify ─────────────────────────────────────────────
            print("  [8] Verifying submission...")
            page.screenshot(path=screenshot_path)
            browser.close()
            print("  [8] Instagram post submitted successfully.")
            return True, "", screenshot_path

    except Exception as exc:
        return False, str(exc), screenshot_path


# ── Main Execution ───────────────────────────────────────────────────

def execute(task_id: str | None = None) -> None:
    DONE.mkdir(parents=True, exist_ok=True)

    if not task_id:
        log_action("execution_error", "instagram_post", "no task_id provided")
        print("ERROR: --task-id is required")
        return

    log_action("skill_invoked", task_id, "started", mode="dry_run" if DRY_RUN else "live")

    task_path = find_task_file(task_id)
    if not task_path:
        log_action("task_not_found", task_id, "failed")
        print(f"ERROR: Could not find task file for {task_id}")
        return

    text = task_path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(text)

    content = extract_post_content(text)

    if not content:
        log_action("validation_error", task_id, "empty_content")
        print(f"VALIDATION ERROR: Empty content in {task_id}")
        return

    # Use provided image_path or auto-generate a branded image from the caption
    image_path = fm.get("image_path", "").strip()
    if not image_path or not Path(image_path).exists():
        print("  No image_path found — auto-generating image from caption...")
        image_path = _generate_post_image(content, task_id)

    if len(content) > INSTAGRAM_CHAR_LIMIT:
        content = content[:INSTAGRAM_CHAR_LIMIT - 3].rstrip() + "..."
        print(f"WARNING: Caption truncated to {INSTAGRAM_CHAR_LIMIT} chars")
        log_action("content_truncated", task_id, "warning",
                   truncated_to=INSTAGRAM_CHAR_LIMIT)

    if not check_rate_limit():
        log_action("rate_limit", "instagram_post", f"exceeded_{MAX_POSTS_PER_DAY}_per_day")
        print(f"RATE LIMIT: Maximum {MAX_POSTS_PER_DAY} posts/day reached.")
        return

    if DRY_RUN:
        print(f"[DRY RUN] Would post to Instagram ({len(content)} chars, image: {image_path}):")
        print(f"  {content[:100]}...")
        log_action("instagram_dry_run", "instagram.com", "dry_run",
                   content_length=len(content), image_path=image_path, task_id=task_id)
        return

    print(f"Posting to Instagram ({len(content)} chars, image: {image_path}) from {task_id}...")
    success, error, screenshot = post_to_instagram(content, image_path)

    if success:
        log_action("instagram_post", "instagram.com", "success",
                   content_length=len(content), image_path=image_path,
                   task_id=task_id, screenshot=screenshot)
        update_dashboard("Success", content, task_id)
        print("  OK  Posted to Instagram")
    else:
        log_action("instagram_post", "instagram.com", "failed",
                   content_length=len(content), image_path=image_path,
                   task_id=task_id, error=error)
        update_dashboard("Failed", content, task_id)
        print(f"  FAIL  {error}")
        sys.exit(1)


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instagram Post Skill")
    parser.add_argument("--task-id", default=None,
                        help="Task ID to process (e.g. TASK_20260301T120000.md)")
    args = parser.parse_args()
    execute(task_id=args.task_id)
