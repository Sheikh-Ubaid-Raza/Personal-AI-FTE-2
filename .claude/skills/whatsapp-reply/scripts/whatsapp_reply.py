"""
AI Employee — WhatsApp Reply Skill (Action Layer)
Sends replies via WhatsApp Web using Playwright browser automation.
Uses persistent session to stay logged in.

Usage (as Claude Code skill):
    python whatsapp_reply.py --chat "Client Name" --message "Your reply text"

Usage (standalone):
    python whatsapp_reply.py --chat "John Doe" --message "Thanks for your message!"
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from rich.console import Console
from rich.panel import Panel

# ── Load .env ────────────────────────────────────────────────────────
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent.parent / ".env")

# ── Paths ────────────────────────────────────────────────────────────
VAULT = Path(__file__).resolve().parent.parent.parent.parent.parent
LOGS = VAULT / "Logs"
SESSION_DIR = VAULT / ".wa_session"

# ── Config ──────────────────────────────────────────────────────────
HEADLESS = os.getenv("WHATSAPP_HEADLESS", "true").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# ── Console ─────────────────────────────────────────────────────────
console = Console()

# ── Logging ─────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    """Append a JSON audit entry to today's log file."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": "whatsapp-reply-skill",
        "action_type": action_type,
        "target": target,
        "result": result,
    }
    entry.update(extra)
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def send_whatsapp_message(chat_name: str, message: str) -> tuple[bool, str]:
    """
    Send a message to a WhatsApp contact via WhatsApp Web.
    
    Args:
        chat_name: Contact name or phone number (as shown in WhatsApp)
        message: Message text to send
    
    Returns:
        (success: bool, error_message: str)
    """
    if DRY_RUN:
        console.print("[yellow][DRY RUN] Would send message to {chat_name}:[/] {message}")
        log_action("whatsapp_reply", chat_name, "dry_run", message=message[:100])
        return True, "[DRY RUN] Message not actually sent"
    
    try:
        with sync_playwright() as p:
            # Launch browser with persistent session
            context = p.chromium.launch_persistent_context(
                str(SESSION_DIR),
                headless=HEADLESS,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            # Navigate to WhatsApp Web
            console.print("[dim]Navigating to WhatsApp Web...[/]")
            page.goto('https://web.whatsapp.com', wait_until='domcontentloaded')
            
            # Wait for chat list or main screen
            try:
                page.wait_for_selector('[data-testid="chat-list"]', timeout=30000)
            except PlaywrightTimeout:
                error_msg = "WhatsApp Web not loaded — please scan QR code or check session"
                console.print(f"[bold red]✗ {error_msg}[/]")
                log_action("whatsapp_reply", chat_name, "session_error", error=error_msg)
                context.close()
                return False, error_msg
            
            # Small delay for content to load
            time.sleep(2)
            
            # Search for the contact
            console.print(f"[dim]Searching for contact: {chat_name}...[/]")
            
            # Click on search box
            search_box = page.query_selector('[data-testid="search"]')
            if not search_box:
                search_box = page.query_selector('input[type="text"]')
            
            if not search_box:
                error_msg = "Search box not found on WhatsApp Web"
                console.print(f"[bold red]✗ {error_msg}[/]")
                log_action("whatsapp_reply", chat_name, "search_error", error=error_msg)
                context.close()
                return False, error_msg
            
            # Clear and type search query
            search_box.fill("")
            search_box.fill(chat_name)
            time.sleep(1)
            
            # Find and click on the contact in search results
            # Try multiple selectors to find the contact
            contact_found = False
            
            # Wait for search results
            time.sleep(2)
            
            # Get all chat items and find matching one
            chat_items = page.query_selector_all('[data-testid="chat-item"]')
            
            for item in chat_items:
                try:
                    name_elem = item.query_selector('span[title]')
                    if name_elem:
                        item_name = name_elem.get_attribute('title')
                        if chat_name.lower() in item_name.lower() or item_name.lower() in chat_name.lower():
                            # Click on this contact
                            item.click()
                            contact_found = True
                            console.print(f"[green]✓ Found contact: {item_name}[/]")
                            break
                except Exception:
                    continue
            
            if not contact_found:
                # Try clicking the first result as fallback
                if chat_items:
                    try:
                        chat_items[0].click()
                        contact_found = True
                        console.print("[yellow]⚠ Clicked first search result (exact match not found)[/]")
                    except Exception as e:
                        pass
            
            if not contact_found:
                error_msg = f"Contact '{chat_name}' not found in WhatsApp"
                console.print(f"[bold red]✗ {error_msg}[/]")
                log_action("whatsapp_reply", chat_name, "contact_not_found", error=error_msg)
                context.close()
                return False, error_msg
            
            # Wait for chat to load
            time.sleep(1)
            
            # Find message input box
            console.print("[dim]Typing message...[/]")
            message_input = page.query_selector('[data-testid="message-input"]')
            
            if not message_input:
                # Try alternative selector
                message_input = page.query_selector('div[contenteditable="true"][data-tab="10"]')
            
            if not message_input:
                error_msg = "Message input box not found"
                console.print(f"[bold red]✗ {error_msg}[/]")
                log_action("whatsapp_reply", chat_name, "input_error", error=error_msg)
                context.close()
                return False, error_msg
            
            # Type the message
            message_input.fill(message)
            time.sleep(0.5)
            
            # Find and click send button
            console.print("[dim]Sending message...[/]")
            send_button = page.query_selector('[data-testid="compose-btn-send"]')
            
            if not send_button:
                # Try alternative: look for send icon
                send_button = page.query_selector('button[aria-label*="Send"]')
            
            if send_button:
                send_button.click()
                time.sleep(1)
                
                # Verify message was sent (look for sent indicator)
                time.sleep(2)
                
                console.print(f"[bold green]✓ Message sent to {chat_name}[/]")
                log_action(
                    "whatsapp_reply", chat_name, "success",
                    message=message[:200],
                    message_length=len(message)
                )
            else:
                # Fallback: press Enter to send
                message_input.press("Enter")
                time.sleep(2)
                console.print(f"[yellow]⚠ Sent via Enter key to {chat_name}[/]")
                log_action(
                    "whatsapp_reply", chat_name, "success_enter_fallback",
                    message=message[:200]
                )
            
            context.close()
            
            return True, ""
            
    except Exception as e:
        error_msg = str(e)
        console.print(f"[bold red]✗ Error sending WhatsApp message: {error_msg}[/]")
        log_action("whatsapp_reply", chat_name, "error", error=error_msg[:200])
        return False, error_msg


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown text."""
    import re
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    fm: dict = {}
    for line in match.group(1).split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm, match.group(2)


def main():
    parser = argparse.ArgumentParser(description="Send WhatsApp message via WhatsApp Web")
    parser.add_argument("--chat", required=False, help="Contact name or phone number")
    parser.add_argument("--message", required=False, help="Message text to send")
    parser.add_argument("--task-id", default="", help="Task ID for logging")

    args = parser.parse_args()

    # Ensure directories exist
    LOGS.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    
    # Read chat and message from args or task file
    chat_name = args.chat
    message = args.message
    
    # If task-id provided but no chat/message, read from task file
    if args.task_id and (not chat_name or not message):
        task_path = VAULT / "Needs_Approval" / args.task_id
        if not task_path.exists():
            task_path = VAULT / "Needs_Action" / args.task_id
        if not task_path.exists():
            task_path = VAULT / "Done" / args.task_id
        
        if task_path.exists():
            text = task_path.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)
            if not chat_name:
                chat_name = fm.get("chat", fm.get("to", ""))
            if not message:
                message = fm.get("message", "")
                # Try to extract from body if not in frontmatter
                if not message:
                    for line in body.split("\n"):
                        if "**Message:**" in line:
                            message = line.split("**Message:**")[1].strip().strip('"')
                            break
    
    if not chat_name or not message:
        console.print("[bold red]ERROR: --chat and --message required, or valid --task-id[/]")
        return 1

    console.print()
    console.print(Panel.fit(
        f"[bold green]WhatsApp Reply Skill[/]\n"
        f"[dim]Sending message to: {chat_name}[/]\n"
        f"[dim]Message length: {len(message)} chars[/]",
        border_style="green",
    ))
    console.print()

    success, error = send_whatsapp_message(chat_name, message)

    if success:
        console.print()
        console.print("[bold green]✓ WhatsApp message sent successfully![/]")
        if args.task_id:
            log_action("task_complete", args.task_id, "success", skill="whatsapp-reply")
        return 0
    else:
        console.print()
        console.print(f"[bold red]✗ Failed to send message: {error}[/]")
        if args.task_id:
            log_action("task_complete", args.task_id, "failed", skill="whatsapp-reply", error=error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
