"""
AI Employee — File Triage Skill (Standalone Script)
====================================================
Scans Needs_Action/ for tasks with status: pending_triage,
classifies them by urgency/type, enriches frontmatter,
updates the Dashboard, and writes a structured audit log.

Usage:
    python triage.py [--dry-run]
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
VAULT         = Path(__file__).resolve().parent.parent.parent.parent.parent
NEEDS_ACTION  = VAULT / "Needs_Action"
DONE          = VAULT / "Done"
LOGS          = VAULT / "Logs"
DASHBOARD     = VAULT / "Dashboard.md"

# ── Classification Rules (top-down, first match wins) ─────────────────
URGENT_KEYWORDS = {
    "urgent", "asap", "deadline", "overdue", "critical", "immediately",
    "emergency", "priority", "action required",
}
ACTIONABLE_KEYWORDS = {
    "invoice", "reply", "report", "payment", "schedule", "send", "create",
    "prepare", "submit", "update", "respond", "call", "meeting", "review",
    "approve", "sign", "draft", "buy", "order", "fix", "resolve",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Logging ────────────────────────────────────────────────────────────

def log_event(target: str, category: str, result: str, **extra) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp":   _now_iso(),
        "actor":       "file-triage-skill",
        "action_type": "triage",
        "target":      target,
        "category":    category,
        "result":      result,
    }
    entry.update(extra)
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Frontmatter Helpers ────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    fm: dict = {}
    for line in match.group(1).split("\n"):
        line = line.strip()
        if not line:
            continue
        idx = line.find(":")
        if idx == -1:
            continue
        fm[line[:idx].strip()] = line[idx + 1:].strip().strip('"').strip("'")
    return fm, match.group(2)


def write_frontmatter(fm: dict, body: str) -> str:
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(body.lstrip("\n"))
    return "\n".join(lines)


# ── Classification ─────────────────────────────────────────────────────

def classify(text: str) -> tuple[str, str]:
    """
    Returns (category, priority) by matching keywords in full file text.
    Top-down: Urgent > Actionable > Informational
    """
    lowered = text.lower()
    for kw in URGENT_KEYWORDS:
        if kw in lowered:
            return "urgent", "high"
    for kw in ACTIONABLE_KEYWORDS:
        if kw in lowered:
            return "actionable", "medium"
    return "informational", "low"


def extract_task_name(body: str, filename: str, max_len: int = 80) -> str:
    for line in body.split("\n"):
        stripped = line.strip().lstrip("#").strip()
        if stripped and stripped not in ("Task Summary", "Full Content", "Objective", "---"):
            return stripped[:max_len]
    return filename


def generate_objective(category: str, task_name: str, fm: dict) -> str:
    """Generate a single imperative objective sentence based on category and task content."""
    prefix = "URGENT: " if category == "urgent" else ""
    skill = fm.get("skill", "")
    source = fm.get("source", "")

    if "invoice" in task_name.lower() or "invoice" in skill.lower():
        return f"{prefix}Prepare and process the invoice as described in '{task_name}'."
    if any(k in task_name.lower() for k in ("reply", "respond", "email")):
        return f"{prefix}Draft and send a response to: '{task_name}'."
    if "report" in task_name.lower():
        return f"{prefix}Compile and deliver the report for: '{task_name}'."
    if "schedule" in task_name.lower() or "meeting" in task_name.lower():
        return f"{prefix}Schedule and confirm the meeting or event for: '{task_name}'."
    if category == "urgent":
        return f"URGENT: Immediately assess and resolve: '{task_name}'."
    if category == "actionable":
        return f"Execute the requested action for: '{task_name}'."
    return f"Review and file the informational item: '{task_name}'."


# ── Dashboard Update ───────────────────────────────────────────────────

def update_dashboard(triaged_items: list[dict]) -> None:
    if not DASHBOARD.exists() or not triaged_items:
        return
    text = DASHBOARD.read_text(encoding="utf-8")
    ts   = _now_iso()

    # Append to Recent Activity
    marker = "| -------------------- | ---------------------------------------------------------- | ------- |"
    if marker in text:
        for item in triaged_items:
            row = (
                f"| {ts} | Triaged {item['file']} → {item['category']} "
                f"(priority: {item['priority']}) | Success |"
            )
            text = text.replace(marker, marker + "\n" + row, 1)

    DASHBOARD.write_text(text, encoding="utf-8")


# ── Main Triage Logic ──────────────────────────────────────────────────

def triage_file(path: Path, dry_run: bool) -> dict | None:
    """
    Process a single task file. Returns a summary dict on success, None if skipped.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"  [SKIP] {path.name}: read error — {exc}")
        return None

    fm, body = parse_frontmatter(raw)
    status   = fm.get("status", "").lower().strip()

    # Idempotency — only process pending_triage files
    if status != "pending_triage":
        return None

    category, priority = classify(raw)
    task_name = extract_task_name(body, path.stem)

    print(f"  {path.name}  →  [{category.upper()}] priority={priority}")

    if dry_run:
        return {"file": path.name, "category": category, "priority": priority}

    # ── Update frontmatter ─────────────────────────────────────────────
    fm["status"]   = category
    fm["priority"] = priority
    fm["triaged"]  = _now_iso()

    # ── Inject ## Objective section for Actionable / Urgent ───────────
    new_body = body
    if category in ("actionable", "urgent"):
        objective = generate_objective(category, task_name, fm)
        if "## Objective" not in body:
            # Insert after the first heading
            heading_match = re.search(r"^#{1,3} .+", new_body, re.MULTILINE)
            if heading_match:
                insert_at = heading_match.end()
                obj_section = f"\n\n## Objective\n\n{objective}\n"
                new_body = new_body[:insert_at] + obj_section + new_body[insert_at:]
            else:
                new_body = f"## Objective\n\n{objective}\n\n" + new_body

    path.write_text(write_frontmatter(fm, new_body), encoding="utf-8")

    log_event(path.name, category, "success", priority=priority, task=task_name)

    return {"file": path.name, "category": category, "priority": priority}


def run(dry_run: bool = False) -> None:
    NEEDS_ACTION.mkdir(parents=True, exist_ok=True)
    ts_start = _now_iso()

    print(f"\nFile Triage — {ts_start}")
    print(f"Scanning {NEEDS_ACTION} …")

    candidates = [
        p for p in sorted(NEEDS_ACTION.glob("*.md"))
        if not p.name.startswith("Plan_")
    ]

    if not candidates:
        print("  No .md files in Needs_Action/.")
        return

    triaged = []
    skipped = 0

    for path in candidates:
        result = triage_file(path, dry_run)
        if result:
            triaged.append(result)
        else:
            skipped += 1

    if not triaged:
        print(f"  No tasks with status=pending_triage found ({skipped} file(s) skipped).")
        return

    print(f"\nTriaged {len(triaged)} file(s), skipped {skipped}:")
    for item in triaged:
        marker = "🔴" if item["category"] == "urgent" else ("🟡" if item["category"] == "actionable" else "🔵")
        print(f"  {marker} {item['file']} → {item['category']} ({item['priority']})")

    if not dry_run:
        update_dashboard(triaged)
        print(f"\nDashboard updated. Logs written to Logs/")

    if dry_run:
        print("\n[DRY RUN] — no files were modified.")


# ── CLI ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="File Triage Skill — AI Employee")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview triage without modifying any files",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
