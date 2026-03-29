"""
AI Employee — Gmail Send Skill (Action Layer)
Sends emails via Gmail SMTP.  Authorization is handled by the
Orchestrator's Checkbox Approval gate — if this script is invoked,
the human has already ticked [x] in the plan.

Usage:
    python send_email.py --task-id TASK_20260215T090000.md
"""

import argparse
import json
import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL", "")
APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
MAX_EMAILS_PER_HOUR = 10

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


# ── Logging ──────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    """Append a JSON audit entry to today's log file."""
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
    """Return True if under the hourly send limit."""
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


# ── Task File Locator ───────────────────────────────────────────────

def find_task_file(task_id: str) -> Path | None:
    """Locate a TASK file across vault directories."""
    name = task_id if task_id.endswith(".md") else task_id + ".md"
    for folder in (NEEDS_APPROVAL, NEEDS_ACTION, DONE):
        candidate = folder / name
        if candidate.exists():
            return candidate
    return None


# ── Email Parameter Extractor ────────────────────────────────────────

def extract_email_params(text: str) -> tuple[str, str, str]:
    """Extract (to, subject, body) from task content using regex.

    Handles natural-language task descriptions like:
      "Send a test email to foo@bar.com with the subject 'Hello' and body 'World'"
    Also checks frontmatter fields (to, subject) as explicit overrides.
    """
    fm, body = parse_frontmatter(text)

    # Try frontmatter fields first (explicit)
    to = fm.get("to", "")
    subject = fm.get("subject", "")
    email_body = fm.get("body", "")

    # Fall back to parsing the body text
    full = body.strip()

    if not to:
        # Find email address in body
        m = EMAIL_REGEX.search(full)
        if m:
            to = m.group(0)

    if not subject:
        # Match: subject 'X' or subject "X" or subject: X
        m = re.search(
            r"subject\s*[:=]?\s*['\"](.+?)['\"]",
            full, re.IGNORECASE,
        )
        if m:
            subject = m.group(1)

    if not email_body:
        # Match: body 'X' or body "X" or body: X
        m = re.search(
            r"body\s*[:=]?\s*['\"](.+?)['\"]",
            full, re.IGNORECASE,
        )
        if m:
            email_body = m.group(1)

    # Last resort: use the whole task text as the body
    if not email_body:
        email_body = full

    return to, subject, email_body


# ── Send Email ───────────────────────────────────────────────────────

def send_email(to: str, subject: str, body: str, cc: str = "") -> tuple[bool, str]:
    """Send an email via Gmail SMTP. Returns (success, error_or_empty)."""
    if DRY_RUN:
        msg = f"[DRY RUN] Would send to={to} subject={subject}"
        print(msg)
        log_action("email_dry_run", to, "dry_run", subject=subject)
        return True, ""

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


# ── Main Execution ───────────────────────────────────────────────────

def execute(task_id: str | None = None) -> None:
    """Run the gmail-send skill.

    Authorization is handled upstream by the Orchestrator's Checkbox
    Approval gate.  This script trusts that if it is invoked, the
    human has already approved the action.
    """
    DONE.mkdir(parents=True, exist_ok=True)

    if not task_id:
        log_action("execution_error", "gmail_send", "no task_id provided")
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

    # ── Extract email parameters ─────────────────────────────────────
    to, subject, email_body = extract_email_params(text)

    # ── Validate ─────────────────────────────────────────────────────
    if not to or not EMAIL_REGEX.match(to):
        log_action("validation_error", task_id,
                   f"Invalid recipient email: {to}")
        print(f"VALIDATION ERROR: Invalid or missing email in {task_id}")
        return

    if not subject:
        subject = f"AI Employee Task: {task_id}"

    # ── Rate Limit ───────────────────────────────────────────────────
    if not check_rate_limit():
        log_action("rate_limit", "gmail_send",
                   f"BLOCKED: Exceeded {MAX_EMAILS_PER_HOUR} emails/hour")
        print(f"RATE LIMIT: Maximum {MAX_EMAILS_PER_HOUR} emails per hour reached.")
        return

    # ── Send ─────────────────────────────────────────────────────────
    print(f"Sending email to {to}: {subject}")
    success, error = send_email(to, subject, email_body)
    now_iso = datetime.now(timezone.utc).isoformat()

    if success:
        log_action("email_sent", to, "success",
                   subject=subject, task_id=task_id,
                   mode="dry_run" if DRY_RUN else "live")
        print(f"  OK  Email sent to {to}")
    else:
        log_action("email_sent", to, "failed",
                   subject=subject, task_id=task_id, error=error)
        print(f"  FAIL  {error}")
        sys.exit(1)


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gmail Send Skill")
    parser.add_argument("--task-id", default=None,
                        help="Task ID to process (e.g. TASK_20260215T090000.md)")
    args = parser.parse_args()
    execute(task_id=args.task_id)
