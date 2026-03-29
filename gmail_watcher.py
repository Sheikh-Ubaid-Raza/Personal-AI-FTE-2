"""
AI Employee — Gmail Watcher (External Perception Layer)
Polls Gmail for unread + important messages and drops markdown
files into AI_Employee_Vault/Inbox/ for the orchestrator pipeline.

Uses the Google Gmail API with OAuth2 credentials.
Follows the BaseWatcher pattern from the hackathon architecture.
"""

import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

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
LOGS = VAULT / "Logs"

# Gmail API scope — read-only (no send/modify)
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Polling interval (seconds) — hackathon doc recommends 120s for Gmail
POLL_INTERVAL = int(os.getenv("GMAIL_POLL_INTERVAL", "120"))

# ── Rich Console ─────────────────────────────────────────────────────
console = Console()

# ── Runtime Stats ────────────────────────────────────────────────────
stats = {
    "started_at": None,
    "emails_processed": 0,
    "errors": 0,
    "last_event": "—",
    "recent_emails": [],  # last 10
}


# ── Logging ──────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    """Append a JSON audit entry to today's log file."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": "gmail_watcher",
        "action_type": action_type,
        "target": target,
        "result": result,
    }
    entry.update(extra)
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Gmail Auth ───────────────────────────────────────────────────────

def get_gmail_service():
    """Authenticate and return a Gmail API service instance.

    Auth flow:
    1. If token.json exists and is valid, use it.
    2. If token is expired, refresh it.
    3. Otherwise, run the OAuth2 consent flow (opens browser).

    Credentials file location is read from GMAIL_CREDENTIALS_FILE env var,
    defaulting to 'credentials.json' in the vault root.
    """
    creds_file = os.getenv(
        "GMAIL_CREDENTIALS_FILE",
        str(VAULT / "credentials.json"),
    )
    token_file = VAULT / "token.json"

    creds = None

    # 1. Try existing token
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    # 2. Refresh or re-auth
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(creds_file).exists():
                console.print(
                    f"[bold red]ERROR:[/] Credentials file not found at "
                    f"[yellow]{creds_file}[/]\n"
                    f"[dim]Download it from Google Cloud Console → APIs & Services "
                    f"→ Credentials → OAuth 2.0 Client ID → Download JSON.\n"
                    f"Save as [bold]{creds_file}[/] or set GMAIL_CREDENTIALS_FILE "
                    f"in .env[/]"
                )
                raise SystemExit(1)
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for next run
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


# ── Email → Markdown ─────────────────────────────────────────────────

def extract_headers(msg: dict) -> dict:
    """Pull common headers from a Gmail message payload."""
    headers = {}
    for h in msg.get("payload", {}).get("headers", []):
        name = h["name"].lower()
        if name in ("from", "to", "subject", "date"):
            headers[name] = h["value"]
    return headers


def build_email_md(msg_id: str, headers: dict, snippet: str) -> str:
    """Build the markdown file content for one email."""
    now_iso = datetime.now(timezone.utc).isoformat()
    sender = headers.get("from", "Unknown")
    subject = headers.get("subject", "No Subject")
    date = headers.get("date", now_iso)
    to = headers.get("to", "—")

    # Sanitize frontmatter values (strip any stray quotes/pipes)
    safe_subject = subject.replace('"', "'").replace("\n", " ")
    safe_sender = sender.replace('"', "'").replace("\n", " ")

    return (
        f"---\n"
        f"type: email\n"
        f'from: "{safe_sender}"\n'
        f'subject: "{safe_subject}"\n'
        f"to: {to}\n"
        f"date: {date}\n"
        f"received: {now_iso}\n"
        f"gmail_id: {msg_id}\n"
        f"priority: high\n"
        f"status: pending\n"
        f"---\n\n"
        f"# {subject}\n\n"
        f"**From:** {sender}\n"
        f"**To:** {to}\n"
        f"**Date:** {date}\n\n"
        f"---\n\n"
        f"## Snippet\n\n"
        f"{snippet}\n\n"
        f"---\n\n"
        f"## Suggested Actions\n\n"
        f"- [ ] Reply to sender\n"
        f"- [ ] Forward to relevant party\n"
        f"- [ ] Archive after processing\n"
    )


# ── Core Watcher Logic ───────────────────────────────────────────────

class GmailWatcher:
    """Polls Gmail for unread+important messages, writes to Inbox/."""

    def __init__(self, service):
        self.service = service
        self.processed_ids: set[str] = set()
        self._seed_processed_ids()

    def _seed_processed_ids(self) -> None:
        """Load already-processed message IDs from existing Inbox files
        to avoid duplicates on restart."""
        for path in INBOX.glob("GMAIL_*.md"):
            # Filename format: GMAIL_<message_id>.md
            msg_id = path.stem.replace("GMAIL_", "")
            self.processed_ids.add(msg_id)

    def check_for_updates(self) -> list[dict]:
        """Fetch unread + important messages not yet processed."""
        try:
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q="is:unread is:important", maxResults=20)
                .execute()
            )
        except Exception as exc:
            stats["errors"] += 1
            stats["last_event"] = f"[red]API ERROR: {exc}[/]"
            log_action("api_error", "gmail_list", str(exc))
            return []

        messages = results.get("messages", [])
        return [m for m in messages if m["id"] not in self.processed_ids]

    def process_message(self, msg_stub: dict) -> Path | None:
        """Fetch full message and write markdown to Inbox/."""
        msg_id = msg_stub["id"]

        try:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="metadata",
                     metadataHeaders=["From", "To", "Subject", "Date"])
                .execute()
            )
        except Exception as exc:
            stats["errors"] += 1
            log_action("api_error", f"gmail_get_{msg_id}", str(exc))
            return None

        headers = extract_headers(msg)
        snippet = msg.get("snippet", "")

        md_content = build_email_md(msg_id, headers, snippet)
        filepath = INBOX / f"GMAIL_{msg_id}.md"

        try:
            filepath.write_text(md_content, encoding="utf-8")
        except Exception as exc:
            stats["errors"] += 1
            log_action("write_error", filepath.name, str(exc))
            return None

        self.processed_ids.add(msg_id)

        stats["emails_processed"] += 1
        subject = headers.get("subject", "No Subject")[:50]
        stats["last_event"] = f"[green]✓ {filepath.name}[/]"
        stats["recent_emails"].append({
            "file": filepath.name,
            "subject": subject,
            "sender": headers.get("from", "?")[:30],
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        })
        stats["recent_emails"] = stats["recent_emails"][-10:]

        log_action("email_captured", filepath.name, "success",
                   gmail_id=msg_id, subject=subject)
        return filepath

    def poll(self) -> int:
        """Run one poll cycle. Returns number of new emails captured."""
        new_messages = self.check_for_updates()
        captured = 0
        for msg_stub in new_messages:
            if self.process_message(msg_stub):
                captured += 1
        return captured


# ── Rich TUI ─────────────────────────────────────────────────────────

def build_status_table() -> Table:
    table = Table(
        title="Gmail Watcher Status",
        title_style="bold red",
        border_style="bright_red",
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

    inbox_count = len(list(INBOX.glob("GMAIL_*.md")))

    table.add_row("Status", "[bold green]● ONLINE[/]")
    table.add_row("Uptime", uptime)
    table.add_row("Poll Interval", f"{POLL_INTERVAL}s")
    table.add_row("Gmail Inbox Files", f"[yellow]{inbox_count}[/]")
    table.add_row("Emails Captured", f"[cyan]{stats['emails_processed']}[/]")
    table.add_row("Errors", f"[red]{stats['errors']}[/]" if stats["errors"] else "0")
    table.add_row("Last Event", stats["last_event"])

    return table


def build_recent_table() -> Table:
    table = Table(
        title="Recent Emails",
        title_style="bold magenta",
        border_style="bright_magenta",
        expand=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Subject", style="bold white")
    table.add_column("From", style="cyan")
    table.add_column("Time", style="green")

    if not stats["recent_emails"]:
        table.add_row("—", "[dim]Waiting for emails…[/]", "—", "—")
    else:
        for i, email in enumerate(reversed(stats["recent_emails"]), 1):
            table.add_row(str(i), email["subject"], email["sender"], email["time"])

    return table


def build_dashboard_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(
            Panel(
                Text.from_markup(
                    "[bold red]  AI EMPLOYEE — GMAIL WATCHER[/]\n"
                    "[dim]External Perception Layer • OAuth2 • Read-Only[/]"
                ),
                border_style="bright_red",
                padding=(1, 2),
            ),
            name="header",
            size=5,
        ),
        Layout(name="body"),
        Layout(
            Panel(
                Text.from_markup(
                    "[dim]Press [bold]Ctrl+C[/bold] to stop  •  "
                    f"Polling every {POLL_INTERVAL}s  •  "
                    "Query: is:unread is:important[/]"
                ),
                border_style="dim",
            ),
            name="footer",
            size=3,
        ),
    )
    layout["body"].split_row(
        Layout(Panel(build_status_table(), border_style="bright_red"), name="status"),
        Layout(Panel(build_recent_table(), border_style="bright_magenta"), name="recent"),
    )
    return layout


# ── Main Loop ────────────────────────────────────────────────────────

def main() -> None:
    for d in (INBOX, LOGS):
        d.mkdir(parents=True, exist_ok=True)

    stats["started_at"] = datetime.now(timezone.utc)

    # ── Authenticate ──────────────────────────────────────────────────
    console.print()
    console.print("[dim]Authenticating with Gmail API…[/]")
    service = get_gmail_service()
    watcher = GmailWatcher(service)
    console.print("[bold green]✓[/] Authenticated successfully\n")

    # ── Banner ────────────────────────────────────────────────────────
    console.print(
        Panel.fit(
            "[bold red]AI EMPLOYEE — GMAIL WATCHER[/]\n"
            "[dim]External Perception Layer v0.1  •  OAuth2  •  Read-Only[/]\n\n"
            f"[white]Output:  [/] [yellow]{INBOX}[/]\n"
            f"[white]Logs:    [/] [yellow]{LOGS}[/]\n"
            f"[white]Query:   [/] [yellow]is:unread is:important[/]\n"
            f"[white]Interval:[/] [yellow]{POLL_INTERVAL}s[/]\n"
            f"[white]Known:   [/] [yellow]{len(watcher.processed_ids)} "
            f"already processed[/]",
            border_style="bright_red",
            padding=(1, 2),
        )
    )
    console.print()

    log_action("gmail_watcher_start", "gmail", "success")

    # ── Graceful shutdown ─────────────────────────────────────────────
    shutdown_requested = False

    def _shutdown(sig, _frame):
        nonlocal shutdown_requested
        shutdown_requested = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── Live Dashboard + Poll Loop ────────────────────────────────────
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
    log_action("gmail_watcher_stop", "gmail", "graceful")

    console.print()
    console.print(
        Panel.fit(
            f"[bold yellow]Gmail Watcher stopped.[/]\n"
            f"[dim]Captured [cyan]{stats['emails_processed']}[/] emails  •  "
            f"[red]{stats['errors']}[/] errors[/]",
            border_style="yellow",
        )
    )


if __name__ == "__main__":
    main()
