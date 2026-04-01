"""
AI Employee — WhatsApp Watcher (Perception Layer)
Monitors WhatsApp Web for unread messages containing keywords like
'invoice', 'help', 'order', 'urgent', 'payment' and creates task files
in /Needs_Action/ for Claude to process.

Uses Playwright for browser automation with persistent session.
Follows the BaseWatcher pattern from gmail_watcher.py.

Usage:
    python whatsapp_watcher.py
"""

import json
import os
import re
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.layout import Layout

# ── Load .env ────────────────────────────────────────────────────────
load_dotenv(Path(__file__).resolve().parent / ".env")

# ── Paths ────────────────────────────────────────────────────────────
VAULT = Path(__file__).resolve().parent
INBOX = VAULT / "Inbox"
NEEDS_ACTION = VAULT / "Needs_Action"
LOGS = VAULT / "Logs"
SESSION_DIR = VAULT / ".wa_session"

# Polling interval (seconds) — WhatsApp Web updates frequently
POLL_INTERVAL = int(os.getenv("WHATSAPP_POLL_INTERVAL", "60"))

# Keywords that indicate a message needs action
ACTION_KEYWORDS = [
    'invoice', 'payment', 'order', 'help', 'urgent', 'asap',
    'deadline', 'money', 'bill', 'due', 'client', 'customer',
    'project', 'deliver', 'send', 'receive', 'transfer'
]

# ── Rich Console ─────────────────────────────────────────────────────
console = Console()

# ── Runtime Stats ────────────────────────────────────────────────────
stats = {
    "started_at": None,
    "messages_processed": 0,
    "errors": 0,
    "last_event": "—",
    "recent_messages": [],  # last 10
}


# ── Logging ──────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    """Append a JSON audit entry to today's log file."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": "whatsapp_watcher",
        "action_type": action_type,
        "target": target,
        "result": result,
    }
    entry.update(extra)
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── WhatsApp Watcher Class ───────────────────────────────────────────

class WhatsAppWatcher:
    """Monitors WhatsApp Web for actionable messages."""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.processed_ids: set[str] = set()
        self._seed_processed_ids()

    def _seed_processed_ids(self) -> None:
        """Load already-processed message IDs from existing task files."""
        for path in INBOX.glob("WHATSAPP_*.md"):
            msg_id = path.stem.replace("WHATSAPP_", "")
            self.processed_ids.add(msg_id)
        # Also check Needs_Action and Done
        for folder in (NEEDS_ACTION, self.vault_path / "Done"):
            if folder.exists():
                for path in folder.glob("WHATSAPP_*.md"):
                    msg_id = path.stem.replace("WHATSAPP_", "")
                    self.processed_ids.add(msg_id)

    def check_whatsapp_messages(self, context) -> list[dict]:
        """
        Check WhatsApp Web for unread messages with action keywords.
        Returns list of new messages to process.
        """
        messages = []
        
        try:
            page = context.pages[0] if context.pages else context.new_page()
            
            # Navigate to WhatsApp Web
            page.goto('https://web.whatsapp.com', wait_until='domcontentloaded')
            
            # Wait for chat list to load (with timeout)
            try:
                page.wait_for_selector('[data-testid="chat-list"]', timeout=30000)
            except PlaywrightTimeout:
                console.print("[bold yellow]⚠ WhatsApp Web not loaded — waiting for QR scan or session...[/]")
                return messages
            
            # Small delay for content to fully load
            time.sleep(2)
            
            # Find all chat items with unread indicators
            # WhatsApp Web structure: chats have aria-label with unread count
            chat_selectors = [
                '[aria-label*="unread"]',
                '[data-testid="chat"]',
            ]
            
            chats = []
            for selector in chat_selectors:
                try:
                    chats = page.query_selector_all(selector)
                    if chats:
                        break
                except Exception:
                    continue
            
            for chat in chats:
                try:
                    # Extract chat info
                    chat_element = chat.query_selector('[data-testid="chat-item"]') or chat
                    
                    # Get the chat name/label
                    name_elem = chat_element.query_selector('[data-testid="chat-item-message"]')
                    if not name_elem:
                        name_elem = chat_element.query_selector('span[title]')
                    
                    chat_name = "Unknown"
                    if name_elem:
                        chat_name = name_elem.inner_text() or name_elem.get_attribute('title') or "Unknown"
                    
                    # Check for unread indicator
                    unread_badge = chat_element.query_selector('[data-testid="unread-count"]')
                    if not unread_badge:
                        # Try alternative selectors
                        unread_badge = chat_element.query_selector('span:has-text("unread")')
                    
                    if not unread_badge:
                        continue  # Skip read chats
                    
                    # Get message preview text
                    message_text = ""
                    preview_elem = chat_element.query_selector('[data-testid="chat-item-message"] span:last-child')
                    if preview_elem:
                        message_text = preview_elem.inner_text().lower()
                    
                    # Check if message contains action keywords
                    matched_keywords = [kw for kw in ACTION_KEYWORDS if kw in message_text]
                    
                    if matched_keywords:
                        # Generate unique ID from chat name + timestamp
                        msg_id = f"{chat_name.replace(' ', '_')}_{int(time.time())}"
                        
                        if msg_id not in self.processed_ids:
                            messages.append({
                                'id': msg_id,
                                'chat_name': chat_name,
                                'message_text': message_text,
                                'matched_keywords': matched_keywords,
                                'timestamp': datetime.now(timezone.utc).isoformat()
                            })
                            console.print(f"[green]✓ Found actionable message from {chat_name}: {message_text[:50]}...[/]")
                    
                except Exception as e:
                    console.print(f"[dim]Error processing chat: {e}[/]")
                    continue
            
        except Exception as e:
            console.print(f"[bold red]Error checking WhatsApp:[/] {e}")
            log_action("whatsapp_check_error", "whatsapp_web", str(e))
        
        return messages

    def build_message_md(self, msg: dict) -> str:
        """Build markdown file content for a WhatsApp message."""
        now_iso = datetime.now(timezone.utc).isoformat()
        
        # Escape special characters for YAML frontmatter
        safe_chat_name = msg['chat_name'].replace('"', "'").replace('\n', ' ')
        safe_message = msg['message_text'].replace('"', "'").replace('\n', ' ')
        keywords_str = ', '.join(msg['matched_keywords'])
        
        return (
            f"---\n"
            f"type: whatsapp_message\n"
            f'from: "{safe_chat_name}"\n'
            f"received: {now_iso}\n"
            f"whatsapp_id: {msg['id']}\n"
            f"keywords: {keywords_str}\n"
            f"priority: high\n"
            f"status: pending\n"
            f"---\n\n"
            f"# WhatsApp Message from {safe_chat_name}\n\n"
            f"**Received:** {now_iso}\n"
            f"**Keywords Detected:** {keywords_str}\n\n"
            f"---\n\n"
            f"## Message Content\n\n"
            f"{safe_message}\n\n"
            f"---\n\n"
            f"## Suggested Actions\n\n"
            f"- [ ] Review message and determine required response\n"
            f"- [ ] Reply via WhatsApp (use whatsapp-reply skill)\n"
            f"- [ ] Create follow-up task if needed\n"
            f"- [ ] Archive after processing\n"
        )

    def process_message(self, msg: dict) -> Path | None:
        """Write WhatsApp message as markdown to Inbox/."""
        md_content = self.build_message_md(msg)
        filepath = INBOX / f"WHATSAPP_{msg['id']}.md"
        
        try:
            filepath.write_text(md_content, encoding="utf-8")
        except Exception as exc:
            stats["errors"] += 1
            log_action("write_error", filepath.name, str(exc))
            return None
        
        self.processed_ids.add(msg['id'])
        
        stats["messages_processed"] += 1
        stats["last_event"] = f"[green]✓ {filepath.name}[/]"
        stats["recent_messages"].append({
            "file": filepath.name,
            "from": msg['chat_name'][:30],
            "keywords": ', '.join(msg['matched_keywords'][:3]),
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        })
        stats["recent_messages"] = stats["recent_messages"][-10:]
        
        log_action("whatsapp_captured", filepath.name, "success",
                   whatsapp_id=msg['id'], chat_name=msg['chat_name'])
        return filepath

    def poll(self) -> int:
        """Run one poll cycle. Returns number of new messages captured."""
        captured = 0
        
        try:
            with sync_playwright() as p:
                # Launch browser with persistent context for session
                context = p.chromium.launch_persistent_context(
                    str(SESSION_DIR),
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                    ]
                )
                
                messages = self.check_whatsapp_messages(context)
                
                for msg in messages:
                    if self.process_message(msg):
                        captured += 1
                
                context.close()
                
        except Exception as e:
            stats["errors"] += 1
            log_action("whatsapp_poll_error", "whatsapp", str(e))
            console.print(f"[bold red]Poll error:[/] {e}")
        
        return captured


# ── Rich TUI ─────────────────────────────────────────────────────────

def build_status_table() -> Table:
    table = Table(
        title="WhatsApp Watcher Status",
        title_style="bold green",
        border_style="bright_green",
        show_lines=True,
        expand=True,
    )
    table.add_column("Metric", style="bold white", min_width=18)
    table.add_column("Value", style="green")
    
    uptime = "—"
    if stats["started_at"]:
        delta = datetime.now(timezone.utc) - stats["started_at"]
        mins, secs = divmod(int(delta.total_seconds()), 60)
        hrs, mins = divmod(mins, 60)
        uptime = f"{hrs:02d}h {mins:02d}m {secs:02d}s"
    
    inbox_count = len(list(INBOX.glob("WHATSAPP_*.md")))
    
    table.add_row("Status", "[bold green]● ONLINE[/]")
    table.add_row("Uptime", uptime)
    table.add_row("Poll Interval", f"{POLL_INTERVAL}s")
    table.add_row("WhatsApp Inbox Files", f"[yellow]{inbox_count}[/]")
    table.add_row("Messages Captured", f"[cyan]{stats['messages_processed']}[/]")
    table.add_row("Errors", f"[red]{stats['errors']}[/]" if stats["errors"] else "0")
    table.add_row("Last Event", stats["last_event"])
    
    return table


def build_recent_table() -> Table:
    table = Table(
        title="Recent WhatsApp Messages",
        title_style="bold magenta",
        border_style="bright_magenta",
        expand=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("From", style="bold white")
    table.add_column("Keywords", style="cyan")
    table.add_column("Time", style="green")
    
    if not stats["recent_messages"]:
        table.add_row("—", "[dim]Waiting for messages…[/]", "—", "—")
    else:
        for i, msg in enumerate(reversed(stats["recent_messages"]), 1):
            table.add_row(str(i), msg["from"], msg["keywords"], msg["time"])
    
    return table


def build_dashboard_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(
            Panel(
                Text.from_markup(
                    "[bold green]  AI EMPLOYEE — WHATSAPP WATCHER[/]\n"
                    "[dim]Perception Layer • Playwright • Keyword Detection[/]"
                ),
                border_style="bright_green",
                padding=(1, 2),
            ),
            name="header",
            size=5,
        ),
        Layout(name="body"),
        Layout(
            Panel(
                Text.from_markup(
                    f"[dim]Press [bold]Ctrl+C[/bold] to stop  •  "
                    f"Polling every {POLL_INTERVAL}s  •  "
                    f"Session: {SESSION_DIR}[/]"
                ),
                border_style="dim",
            ),
            name="footer",
            size=3,
        ),
    )
    layout["body"].split_row(
        Layout(Panel(build_status_table(), border_style="bright_green"), name="status"),
        Layout(Panel(build_recent_table(), border_style="bright_magenta"), name="recent"),
    )
    return layout


# ── Main Loop ────────────────────────────────────────────────────────

def main() -> None:
    # Ensure directories exist
    for d in (INBOX, NEEDS_ACTION, LOGS, SESSION_DIR):
        d.mkdir(parents=True, exist_ok=True)
    
    stats["started_at"] = datetime.now(timezone.utc)
    
    # ── Banner ────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel.fit(
            "[bold green]AI EMPLOYEE — WHATSAPP WATCHER[/]\n"
            "[dim]Perception Layer v0.1  •  Playwright  •  Keyword Detection[/]\n\n"
            f"[white]Output:    [/] [yellow]{INBOX}[/]\n"
            f"[white]Logs:      [/] [yellow]{LOGS}[/]\n"
            f"[white]Session:   [/] [yellow]{SESSION_DIR}[/]\n"
            f"[white]Interval:  [/] [yellow]{POLL_INTERVAL}s[/]\n"
            f"[white]Keywords:  [/] [yellow]{', '.join(ACTION_KEYWORDS[:5])}...[/]",
            border_style="bright_green",
            padding=(1, 2),
        )
    )
    console.print()
    
    log_action("whatsapp_watcher_start", "whatsapp", "success")
    
    # ── Graceful shutdown ─────────────────────────────────────────────
    shutdown_requested = False
    
    def _shutdown(sig, _frame):
        nonlocal shutdown_requested
        shutdown_requested = True
    
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    
    # ── Live Dashboard + Poll Loop ────────────────────────────────────
    watcher = WhatsAppWatcher(VAULT)
    
    try:
        with Live(build_dashboard_layout(), console=console, refresh_per_second=1) as live:
            while not shutdown_requested:
                watcher.poll()
                live.update(build_dashboard_layout())
                
                for _ in range(POLL_INTERVAL):
                    if shutdown_requested:
                        break
                    time.sleep(1)
                    live.update(build_dashboard_layout())
                    
    except KeyboardInterrupt:
        pass
    
    # ── Goodbye ───────────────────────────────────────────────────────
    log_action("whatsapp_watcher_stop", "whatsapp", "graceful")
    
    console.print()
    console.print(
        Panel.fit(
            f"[bold yellow]WhatsApp Watcher stopped.[/]\n"
            f"[dim]Captured [cyan]{stats['messages_processed']}[/] messages  •  "
            f"[red]{stats['errors']}[/] errors[/]",
            border_style="yellow",
        )
    )


if __name__ == "__main__":
    main()
