"""
AI Employee — Inbox Watcher (Perception Layer)
Monitors AI_Employee_Vault/Inbox/ for new .md files and creates
triaged task files in Needs_Action/.
"""

import json
import logging
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
from rich.logging import RichHandler

# ── Paths ────────────────────────────────────────────────────────────
VAULT = Path(__file__).resolve().parent
INBOX = VAULT / "Inbox"
NEEDS_ACTION = VAULT / "Needs_Action"
LOGS = VAULT / "Logs"

# ── Rich Console ─────────────────────────────────────────────────────
console = Console()

# ── Logging (Rich + file) ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[
        RichHandler(
            console=console,
            rich_tracebacks=True,
            show_path=False,
            markup=True,
        ),
        logging.FileHandler(LOGS / "watcher.log"),
    ],
)
logger = logging.getLogger("InboxWatcher")

# ── Runtime Stats ────────────────────────────────────────────────────
stats = {
    "started_at": None,
    "files_processed": 0,
    "errors": 0,
    "last_event": "—",
    "recent_tasks": [],  # last 10 task names
}


def log_action(action_type: str, target: str, result: str) -> None:
    """Append a JSON audit entry to today's log file."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": "inbox_watcher",
        "action_type": action_type,
        "target": target,
        "result": result,
    }
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def build_task_md(source_name: str, content: str) -> str:
    """Return the Markdown string for a Needs_Action task file."""
    now = datetime.now(timezone.utc).isoformat()
    summary = content.strip().replace("\n", " ")[:100]
    return (
        f"---\n"
        f"type: task_notification\n"
        f"source: Inbox\n"
        f"original_file: {source_name}\n"
        f"created: {now}\n"
        f"status: pending_triage\n"
        f"priority: medium\n"
        f"---\n\n"
        f"# Task Summary\n\n"
        f"{summary}\n\n"
        f"---\n\n"
        f"## Full Content\n\n"
        f"{content}\n"
    )


def build_status_table() -> Table:
    """Build a live-updating status table."""
    table = Table(
        title="Watcher Status",
        title_style="bold cyan",
        border_style="bright_blue",
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

    inbox_count = len(list(INBOX.glob("*.md")))
    needs_count = len(list(NEEDS_ACTION.glob("*.md")))

    table.add_row("Status", "[bold green]● ONLINE[/]")
    table.add_row("Uptime", uptime)
    table.add_row("Monitoring", str(INBOX))
    table.add_row("Inbox Files", f"[yellow]{inbox_count}[/]")
    table.add_row("Needs Action", f"[yellow]{needs_count}[/]")
    table.add_row("Processed", f"[cyan]{stats['files_processed']}[/]")
    table.add_row("Errors", f"[red]{stats['errors']}[/]" if stats["errors"] else "0")
    table.add_row("Last Event", stats["last_event"])

    return table


def build_recent_table() -> Table:
    """Build table of recently created tasks."""
    table = Table(
        title="Recent Tasks",
        title_style="bold magenta",
        border_style="bright_magenta",
        expand=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Task File", style="bold white")
    table.add_column("Source", style="cyan")
    table.add_column("Time", style="green")

    if not stats["recent_tasks"]:
        table.add_row("—", "[dim]Waiting for files…[/]", "—", "—")
    else:
        for i, task in enumerate(reversed(stats["recent_tasks"]), 1):
            table.add_row(str(i), task["name"], task["source"], task["time"])

    return table


def build_dashboard() -> Layout:
    """Compose the full Rich dashboard layout."""
    layout = Layout()
    layout.split_column(
        Layout(
            Panel(
                Text.from_markup(
                    "[bold cyan]  AI EMPLOYEE — INBOX WATCHER[/]\n"
                    "[dim]Perception Layer • Local-First • Autonomous[/]"
                ),
                border_style="bright_cyan",
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
                    "Logs → Logs/watcher.log  •  "
                    "Polling every 2s[/]"
                ),
                border_style="dim",
            ),
            name="footer",
            size=3,
        ),
    )
    layout["body"].split_row(
        Layout(Panel(build_status_table(), border_style="bright_blue"), name="status"),
        Layout(Panel(build_recent_table(), border_style="bright_magenta"), name="recent"),
    )
    return layout


class InboxHandler(FileSystemEventHandler):
    """React to new .md files landing in Inbox/."""

    def __init__(self):
        super().__init__()
        self._processed: set[str] = set()

    def on_created(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.suffix.lower() != ".md":
            return

        # Deduplicate — PollingObserver on WSL2 can fire twice
        file_key = str(path.resolve())
        if file_key in self._processed:
            logger.debug("Skipping duplicate event for %s", path.name)
            return
        self._processed.add(file_key)

        # Small delay so the writing process can finish flushing
        time.sleep(0.5)

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            stats["errors"] += 1
            stats["last_event"] = f"[red]READ ERROR: {path.name}[/]"
            logger.error("Failed to read [bold]%s[/]: %s", path.name, exc)
            log_action("read_error", path.name, str(exc))
            return

        _now = datetime.now(timezone.utc)
        stamp = _now.strftime("%Y%m%dT%H%M%S") + f"_{_now.microsecond // 1000:03d}"
        task_name = f"TASK_{stamp}.md"
        task_path = NEEDS_ACTION / task_name

        try:
            task_path.write_text(
                build_task_md(path.name, content), encoding="utf-8"
            )
            stats["files_processed"] += 1
            stats["last_event"] = f"[green]✓ {task_name}[/]"
            stats["recent_tasks"].append({
                "name": task_name,
                "source": path.name,
                "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            })
            # Keep only last 10
            stats["recent_tasks"] = stats["recent_tasks"][-10:]

            logger.info(
                "[bold green]✓[/] Created [bold]%s[/]  ←  [cyan]%s[/]",
                task_name,
                path.name,
            )
            log_action("task_created", task_name, "success")
        except Exception as exc:
            stats["errors"] += 1
            stats["last_event"] = f"[red]WRITE ERROR: {task_name}[/]"
            logger.error("Failed to write task for [bold]%s[/]: %s", path.name, exc)
            log_action("write_error", task_name, str(exc))


def main() -> None:
    for d in (INBOX, NEEDS_ACTION, LOGS):
        d.mkdir(parents=True, exist_ok=True)

    stats["started_at"] = datetime.now(timezone.utc)

    # ── Banner ────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]AI EMPLOYEE — INBOX WATCHER[/]\n"
            "[dim]Perception Layer v0.1  •  Local-First  •  Autonomous[/]\n\n"
            f"[white]Monitoring:[/] [yellow]{INBOX}[/]\n"
            f"[white]Output:    [/] [yellow]{NEEDS_ACTION}[/]\n"
            f"[white]Logs:      [/] [yellow]{LOGS}[/]",
            border_style="bright_cyan",
            padding=(1, 2),
        )
    )
    console.print()

    # ── Observer ──────────────────────────────────────────────────────
    observer = PollingObserver(timeout=2)
    observer.schedule(InboxHandler(), str(INBOX), recursive=False)
    observer.start()

    logger.info("[bold green]Watcher started[/] — monitoring [cyan]%s[/]", INBOX)
    log_action("watcher_start", str(INBOX), "success")

    # ── Graceful shutdown ─────────────────────────────────────────────
    shutdown_requested = False

    def _shutdown(sig, _frame):
        nonlocal shutdown_requested
        shutdown_requested = True
        logger.info(
            "[bold yellow]Received %s[/] — shutting down gracefully…",
            signal.Signals(sig).name,
        )
        log_action("watcher_stop", str(INBOX), "graceful")
        observer.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── Live Dashboard ────────────────────────────────────────────────
    try:
        with Live(build_dashboard(), console=console, refresh_per_second=1) as live:
            while observer.is_alive():
                live.update(build_dashboard())
                time.sleep(1)
    except KeyboardInterrupt:
        if not shutdown_requested:
            log_action("watcher_stop", str(INBOX), "graceful")
            observer.stop()

    observer.join()

    # ── Goodbye ───────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel.fit(
            f"[bold yellow]Watcher stopped.[/]\n"
            f"[dim]Processed [cyan]{stats['files_processed']}[/] files  •  "
            f"[red]{stats['errors']}[/] errors[/]",
            border_style="yellow",
        )
    )


if __name__ == "__main__":
    main()
