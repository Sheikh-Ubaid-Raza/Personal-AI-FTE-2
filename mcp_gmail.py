"""
MCP Server — Gmail Send
Exposes send_email, list_pending_approvals, and check_email_status as MCP tools.
Transport: stdio (standard for Claude Code).
"""

import json
import os
import re
import shutil
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ── Paths ────────────────────────────────────────────────────────────
VAULT = Path(__file__).resolve().parent
APPROVED = VAULT / "Approved"
DONE = VAULT / "Done"
LOGS = VAULT / "Logs"

load_dotenv(VAULT / ".env")

# ── Config ───────────────────────────────────────────────────────────
SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL", "")
APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
MAX_EMAILS_PER_HOUR = 10

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

# ── Helpers ──────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": "gmail-send-skill",
        "action_type": action_type,
        "target": target,
        "result": result,
    }
    entry.update(extra)
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def parse_frontmatter(text: str) -> tuple[dict, str]:
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


def build_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for key, value in fm.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def check_rate_limit() -> bool:
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    if not log_file.exists():
        return True
    one_hour_ago = datetime.now(timezone.utc).timestamp() - 3600
    count = 0
    for line in log_file.read_text(encoding="utf-8").strip().split("\n"):
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (entry.get("actor") == "gmail-send-skill"
                and entry.get("action_type") == "email_sent"
                and entry.get("result") == "success"):
            ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
            if ts > one_hour_ago:
                count += 1
    return count < MAX_EMAILS_PER_HOUR


def _smtp_send(to: str, subject: str, body: str, cc: str = "") -> tuple[bool, str]:
    if DRY_RUN:
        log_action("email_dry_run", to, "dry_run", subject=subject)
        return True, "[DRY RUN] Email not actually sent."

    if not SENDER_EMAIL or not APP_PASSWORD:
        err = "GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD not set in .env"
        log_action("config_error", "gmail_send", err)
        return False, err

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body.strip(), "plain", "utf-8"))

    recipients = [to]
    if cc:
        recipients.extend(addr.strip() for addr in cc.split(","))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
        return True, ""
    except Exception as exc:
        return False, str(exc)


# ── MCP Server ───────────────────────────────────────────────────────

mcp = FastMCP("gmail")


@mcp.tool()
def send_email(to: str, subject: str, body: str, cc: str = "") -> str:
    """Send an email via Gmail SMTP.

    Creates an approval record, validates, sends, and archives to Done/.
    Rate-limited to 10 emails/hour. Respects DRY_RUN env flag.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text email body.
        cc: Optional comma-separated CC addresses.
    """
    APPROVED.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)

    # Validate
    if not to or not EMAIL_REGEX.match(to):
        log_action("validation_error", to, f"Invalid recipient email: {to}")
        return f"Error: Invalid email address '{to}'."

    if not subject:
        log_action("validation_error", "send_email", "Missing subject")
        return "Error: Subject is required."

    if not body.strip():
        log_action("validation_error", "send_email", "Empty email body")
        return "Error: Email body cannot be empty."

    # Rate limit
    if not check_rate_limit():
        log_action("rate_limit", "gmail_send",
                   f"BLOCKED: Exceeded {MAX_EMAILS_PER_HOUR} emails/hour")
        return f"Error: Rate limit reached ({MAX_EMAILS_PER_HOUR} emails/hour)."

    # Create approval record
    now = datetime.now(timezone.utc)
    task_id = f"MCP_{now.strftime('%Y%m%dT%H%M%S')}"
    fm = {
        "action": "send_email",
        "status": "approved",
        "to": to,
        "subject": subject,
        "source": "mcp_gmail",
        "created_at": now.isoformat(),
    }
    if cc:
        fm["cc"] = cc
    filename = f"{task_id}_send_email.md"
    approval_path = APPROVED / filename
    approval_path.write_text(
        build_frontmatter(fm) + "\n" + body, encoding="utf-8"
    )

    # Send
    success, error = _smtp_send(to, subject, body, cc)
    now_iso = datetime.now(timezone.utc).isoformat()

    if success:
        fm["status"] = "executed"
        fm["executed_at"] = now_iso
        log_action("email_sent", to, "success",
                   subject=subject, approval_file=filename)
        result_msg = f"Email sent to {to}."
        if DRY_RUN:
            result_msg = f"[DRY RUN] Would send email to {to}."
    else:
        fm["status"] = "failed"
        fm["error"] = error
        log_action("email_sent", to, "failed",
                   subject=subject, approval_file=filename, error=error)
        result_msg = f"Failed to send email: {error}"

    # Update and archive
    approval_path.write_text(
        build_frontmatter(fm) + "\n" + body, encoding="utf-8"
    )
    try:
        shutil.move(str(approval_path), str(DONE / filename))
    except Exception as exc:
        log_action("move_error", filename, str(exc))

    return result_msg


@mcp.tool()
def list_pending_approvals() -> str:
    """List all pending approved send_email files in the Approved/ folder.

    Returns a summary of each pending approval with recipient, subject, and filename.
    Read-only — does not modify any files.
    """
    APPROVED.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sorted(APPROVED.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        fm, _ = parse_frontmatter(text)
        if fm.get("action") != "send_email" or fm.get("status") != "approved":
            continue
        results.append(
            f"- {path.name}: to={fm.get('to', '?')} subject={fm.get('subject', '?')}"
        )

    if not results:
        return "No pending approved emails found."
    return f"Found {len(results)} pending approval(s):\n" + "\n".join(results)


@mcp.tool()
def check_email_status(task_id: str) -> str:
    """Check the execution status of a previously sent email by task ID.

    Searches the Done/ folder for a matching approval file and returns its status.

    Args:
        task_id: The task identifier (e.g. MCP_20260216T120000).
    """
    DONE.mkdir(parents=True, exist_ok=True)
    for path in DONE.glob("*.md"):
        if task_id not in path.name:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        fm, _ = parse_frontmatter(text)
        status = fm.get("status", "unknown")
        to = fm.get("to", "?")
        subject = fm.get("subject", "?")
        executed_at = fm.get("executed_at", "?")
        error = fm.get("error", "")
        info = f"Task: {task_id}\nFile: {path.name}\nStatus: {status}\nTo: {to}\nSubject: {subject}\nExecuted: {executed_at}"
        if error:
            info += f"\nError: {error}"
        return info

    return f"No record found for task ID '{task_id}' in Done/."


if __name__ == "__main__":
    mcp.run(transport="stdio")
