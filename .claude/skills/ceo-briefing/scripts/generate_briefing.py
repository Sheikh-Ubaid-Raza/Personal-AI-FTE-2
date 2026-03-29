"""
AI Employee — CEO Briefing Skill (Intelligence Layer)
Generates the weekly "Monday Morning CEO Briefing" in Briefings/.

Data sources:
  • Done/          — completed tasks from the last N days (filesystem)
  • Odoo JSON-RPC  — revenue, invoices, overdue AR (optional; skipped if offline)

Usage:
    python generate_briefing.py [--days 7] [--task-id TASK_ID]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── Paths ─────────────────────────────────────────────────────────────
VAULT     = Path(__file__).resolve().parent.parent.parent.parent.parent
DONE      = VAULT / "Done"
BRIEFINGS = VAULT / "Briefings"
LOGS      = VAULT / "Logs"
DASHBOARD = VAULT / "Dashboard.md"

load_dotenv(VAULT / ".env")

# ── Config ────────────────────────────────────────────────────────────
ODOO_URL      = os.getenv("ODOO_URL",      "http://localhost:8069").rstrip("/")
ODOO_DB       = os.getenv("ODOO_DB",       "")
ODOO_USER     = os.getenv("ODOO_USER",     "")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "")
DRY_RUN       = os.getenv("DRY_RUN",       "false").lower() == "true"

# Bottleneck threshold: tasks taking longer than this are flagged
BOTTLENECK_HOURS = 48

# Subscription cost flag: flag any vendor bill over this amount
SUBSCRIPTION_FLAG_THRESHOLD = 50.0

# ── Logging ───────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "actor":       "ceo-briefing",
        "action_type": action_type,
        "target":      target,
        "result":      result,
    }
    entry.update(extra)
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def update_dashboard(description: str, result: str) -> None:
    if not DASHBOARD.exists():
        return
    text   = DASHBOARD.read_text(encoding="utf-8")
    ts     = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    row    = f"| {ts} | CEO Briefing: {description} | {result} |"
    marker = "| -------------------- | ---------------------------------------------------------- | ------- |"
    if marker in text:
        text = text.replace(marker, marker + "\n" + row)
        DASHBOARD.write_text(text, encoding="utf-8")


# ── Frontmatter Parser ────────────────────────────────────────────────

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


# ── Odoo JSON-RPC Client ──────────────────────────────────────────────

_odoo_uid: int | None = None
_odoo_available: bool | None = None  # None = not tested yet


def _jsonrpc(service: str, method: str, args: list, timeout: int = 15) -> object:
    payload = {
        "jsonrpc": "2.0",
        "method":  "call",
        "id":      1,
        "params":  {"service": service, "method": method, "args": args},
    }
    resp = requests.post(f"{ODOO_URL}/web/jsonrpc", json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        msg = (
            (data["error"].get("data") or {}).get("message")
            or data["error"].get("message", str(data["error"]))
        )
        raise RuntimeError(f"Odoo RPC error: {msg}")
    return data["result"]


def odoo_authenticate() -> int | None:
    """Authenticate and return UID, or None if Odoo is unavailable."""
    global _odoo_uid, _odoo_available
    if _odoo_available is False:
        return None
    if _odoo_uid is not None:
        return _odoo_uid
    if not all([ODOO_DB, ODOO_USER, ODOO_PASSWORD]):
        _odoo_available = False
        return None
    try:
        uid = _jsonrpc("common", "authenticate",
                       [ODOO_DB, ODOO_USER, ODOO_PASSWORD, {}], timeout=10)
        if not uid:
            _odoo_available = False
            return None
        _odoo_uid = uid
        _odoo_available = True
        return uid
    except Exception as exc:
        _odoo_available = False
        print(f"  [Odoo] Connection failed: {exc} — financial data will be skipped.")
        return None


def odoo_execute(model: str, method: str,
                 args: list | None = None,
                 kwargs: dict | None = None) -> object | None:
    """Run an Odoo execute_kw call. Returns None if Odoo is offline."""
    uid = odoo_authenticate()
    if uid is None:
        return None
    try:
        return _jsonrpc("object", "execute_kw",
                        [ODOO_DB, uid, ODOO_PASSWORD, model, method,
                         args or [], kwargs or {}])
    except Exception as exc:
        print(f"  [Odoo] Query failed: {exc}")
        return None


def _fmt(amount: float) -> str:
    return f"${amount:,.2f}"


# ── Done Folder Scanner ───────────────────────────────────────────────

def scan_done_folder(since: datetime) -> dict:
    """
    Scan Done/ for files modified after `since`.
    Returns a summary dict with completed tasks, skill breakdown,
    and any detected bottlenecks.
    """
    completed: list[dict] = []
    bottlenecks: list[dict] = []

    for path in sorted(DONE.glob("*.md")):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except Exception:
            continue
        if mtime < since:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        fm, body = parse_frontmatter(text)
        status = fm.get("status", "unknown")

        # Only count tasks that were successfully executed or approved
        if status not in ("executed", "done", "approved", "completed"):
            continue

        # Extract a human-readable task name
        task_name = ""
        for line in body.split("\n"):
            stripped = line.strip().lstrip("#").strip()
            if stripped and stripped not in ("Task Summary", "Full Content",
                                              "Objective", "---"):
                task_name = stripped[:80]
                break
        if not task_name:
            task_name = path.stem

        skill     = fm.get("executed_by", fm.get("skill", "—"))
        created   = fm.get("created",     fm.get("triaged", ""))
        executed  = fm.get("executed_at", "")

        # Bottleneck detection: > BOTTLENECK_HOURS from creation to execution
        delay_hours: float | None = None
        if created and executed:
            try:
                t_start = datetime.fromisoformat(created.replace("Z", "+00:00"))
                t_end   = datetime.fromisoformat(executed.replace("Z", "+00:00"))
                delay_hours = (t_end - t_start).total_seconds() / 3600
            except Exception:
                pass

        completed.append({
            "file":        path.name,
            "task":        task_name,
            "skill":       skill,
            "status":      status,
            "created":     created,
            "executed_at": executed,
            "delay_hours": delay_hours,
        })

        if delay_hours is not None and delay_hours > BOTTLENECK_HOURS:
            bottlenecks.append({
                "task":        task_name,
                "delay_hours": delay_hours,
                "skill":       skill,
            })

    # Skill breakdown counts
    skill_counts: dict[str, int] = {}
    for item in completed:
        k = item["skill"] or "unknown"
        skill_counts[k] = skill_counts.get(k, 0) + 1

    return {
        "completed":    completed,
        "bottlenecks":  bottlenecks,
        "skill_counts": skill_counts,
        "total":        len(completed),
    }


# ── Odoo Financial Fetcher ────────────────────────────────────────────

def fetch_financial_data(since: datetime) -> dict:
    """
    Pull this week's revenue and outstanding invoices from Odoo.
    Returns a summary dict. All monetary values are floats (USD or company default).
    Returns empty dict with odoo_online=False if Odoo is unreachable.
    """
    since_str = since.strftime("%Y-%m-%d")
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    uid = odoo_authenticate()
    if uid is None:
        return {
            "odoo_online":      False,
            "week_revenue":     0.0,
            "week_invoices":    [],
            "overdue_invoices": [],
            "total_outstanding": 0.0,
            "total_overdue":    0.0,
        }

    # This week's posted customer invoices
    week_invoices_raw = odoo_execute("account.move", "search_read",
        [[
            ["move_type",     "=", "out_invoice"],
            ["state",         "=", "posted"],
            ["invoice_date",  ">=", since_str],
            ["invoice_date",  "<=", today_str],
        ]],
        {"fields": ["name", "partner_id", "invoice_date",
                    "amount_total", "payment_state"]},
    ) or []

    week_revenue = sum(inv["amount_total"] for inv in week_invoices_raw)
    week_invoices = [
        {
            "ref":     inv["name"],
            "partner": inv["partner_id"][1] if inv["partner_id"] else "—",
            "date":    inv.get("invoice_date", "—"),
            "amount":  inv["amount_total"],
            "paid":    inv["payment_state"] == "paid",
        }
        for inv in week_invoices_raw
    ]

    # All overdue posted invoices
    overdue_raw = odoo_execute("account.move", "search_read",
        [[
            ["move_type",          "=",  "out_invoice"],
            ["state",              "=",  "posted"],
            ["invoice_date_due",   "<",  today_str],
            ["payment_state",      "not in", ["paid", "reversed"]],
        ]],
        {"fields": ["name", "partner_id", "invoice_date_due", "amount_residual"]},
    ) or []

    total_outstanding = odoo_execute("account.move", "search_read",
        [[
            ["move_type",     "=", "out_invoice"],
            ["state",         "=", "posted"],
            ["payment_state", "not in", ["paid", "reversed"]],
        ]],
        {"fields": ["amount_residual"]},
    ) or []

    total_outstanding_amt = sum(
        inv["amount_residual"] for inv in total_outstanding
    )
    total_overdue_amt = sum(inv["amount_residual"] for inv in overdue_raw)

    overdue_invoices = [
        {
            "ref":     inv["name"],
            "partner": inv["partner_id"][1] if inv["partner_id"] else "—",
            "due":     inv.get("invoice_date_due", "—"),
            "amount":  inv["amount_residual"],
        }
        for inv in overdue_raw
    ]

    return {
        "odoo_online":       True,
        "week_revenue":      week_revenue,
        "week_invoices":     week_invoices,
        "overdue_invoices":  overdue_invoices,
        "total_outstanding": total_outstanding_amt,
        "total_overdue":     total_overdue_amt,
    }


# ── Briefing Renderer ─────────────────────────────────────────────────

def render_briefing(since: datetime, vault_data: dict, fin: dict) -> str:
    """Render the full CEO Briefing markdown."""
    now       = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    since_str = since.strftime("%Y-%m-%d")
    ts        = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    completed   = vault_data["completed"]
    bottlenecks = vault_data["bottlenecks"]
    skill_counts = vault_data["skill_counts"]
    total       = vault_data["total"]

    # ── Executive Summary ─────────────────────────────────────────────
    if fin.get("odoo_online"):
        revenue_str = _fmt(fin["week_revenue"])
        fin_summary = (
            f"{total} task(s) completed this week; "
            f"{revenue_str} revenue from {len(fin['week_invoices'])} invoice(s)."
        )
    else:
        fin_summary = (
            f"{total} task(s) completed this week; "
            f"Odoo offline — financial data unavailable."
        )

    # ── Revenue Section ───────────────────────────────────────────────
    if fin.get("odoo_online"):
        rev_rows = ""
        for inv in fin["week_invoices"]:
            paid_flag = " ✓" if inv["paid"] else ""
            rev_rows += (
                f"| {inv['ref']:<22} | {inv['partner'][:28]:<28} "
                f"| {inv['date']:<12} | {_fmt(inv['amount']):>12}{paid_flag} |\n"
            )
        if not rev_rows:
            rev_rows = "| —  | No invoices posted this week | — | — |\n"

        revenue_section = f"""## Revenue

| Reference               | Partner                       | Date         |       Amount |
| ----------------------- | ----------------------------- | ------------ | ------------ |
{rev_rows}
**This Week Total  : {_fmt(fin['week_revenue'])}**
**Total Outstanding: {_fmt(fin['total_outstanding'])}**
"""
    else:
        revenue_section = """## Revenue

> **Odoo Offline** — Connect Odoo at `http://localhost:8069` to enable financial tracking.
"""

    # ── Completed Tasks ───────────────────────────────────────────────
    if completed:
        completed_lines = ""
        for item in completed:
            skill_tag = f" `[{item['skill']}]`" if item["skill"] and item["skill"] != "—" else ""
            completed_lines += f"- [x] {item['task']}{skill_tag}\n"
    else:
        completed_lines = "_No tasks completed in the past 7 days._\n"

    # ── Skill Breakdown ───────────────────────────────────────────────
    skill_rows = ""
    for skill, count in sorted(skill_counts.items(), key=lambda x: -x[1]):
        skill_rows += f"| {skill:<20} | {count:>5} |\n"
    if not skill_rows:
        skill_rows = "| — | 0 |\n"

    # ── Bottlenecks ───────────────────────────────────────────────────
    if bottlenecks:
        bottleneck_rows = ""
        for b in bottlenecks:
            expected = f"{BOTTLENECK_HOURS}h"
            actual   = f"{b['delay_hours']:.0f}h"
            delay    = f"+{b['delay_hours'] - BOTTLENECK_HOURS:.0f}h"
            bottleneck_rows += (
                f"| {b['task'][:45]:<45} | {expected:>8} | {actual:>8} | {delay:>8} |\n"
            )
        bottleneck_section = f"""## Bottlenecks

| Task                                          | Expected | Actual   |    Delay |
| --------------------------------------------- | -------- | -------- | -------- |
{bottleneck_rows}"""
    else:
        bottleneck_section = "## Bottlenecks\n\n_No bottlenecks this week — all tasks completed within SLA._\n"

    # ── Proactive Suggestions ─────────────────────────────────────────
    suggestions = []
    if fin.get("odoo_online") and fin["overdue_invoices"]:
        for inv in fin["overdue_invoices"][:3]:
            suggestions.append(
                f"**Overdue Invoice:** {inv['ref']} from {inv['partner']} "
                f"({_fmt(inv['amount'])} due {inv['due']}) — "
                f"follow up or send reminder."
            )
    if not suggestions:
        suggestions.append("No proactive suggestions this week — finances look healthy.")

    suggestions_md = "\n".join(f"- {s}" for s in suggestions)

    # ── Assemble ──────────────────────────────────────────────────────
    briefing = f"""---
type: ceo_briefing
generated: {ts}
period: {since_str} to {today_str}
tasks_completed: {total}
odoo_online: {str(fin.get('odoo_online', False)).lower()}
---

# Monday Morning CEO Briefing

*Period: {since_str} → {today_str}  |  Generated: {ts}*

## Executive Summary

{fin_summary}

{revenue_section}
## Completed Tasks ({total} total)

{completed_lines}
### Skill Breakdown

| Skill                | Count |
| -------------------- | ----- |
{skill_rows}
{bottleneck_section}

## Proactive Suggestions

{suggestions_md}

---
*Generated by AI Employee CEO Briefing skill v0.1*
"""
    return briefing


# ── Main ──────────────────────────────────────────────────────────────

def run(days: int = 7, task_id: str | None = None) -> None:
    BRIEFINGS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    now   = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    log_action("briefing_started", "ceo-briefing", "in_progress",
               period_days=days, task_id=task_id or "scheduled")

    print(f"Scanning Done/ for tasks since {since.strftime('%Y-%m-%d')}…")
    vault_data = scan_done_folder(since)
    print(f"  Found {vault_data['total']} completed task(s).")

    print("Fetching financial data from Odoo…")
    fin = fetch_financial_data(since)
    if fin.get("odoo_online"):
        print(f"  Odoo online. Week revenue: {_fmt(fin['week_revenue'])}")
    else:
        print("  Odoo offline — financial section will be skipped.")

    briefing_md = render_briefing(since, vault_data, fin)

    if DRY_RUN:
        print("\n[DRY RUN] Briefing content:\n")
        print(briefing_md)
        log_action("briefing_dry_run", "ceo-briefing", "success",
                   tasks_completed=vault_data["total"],
                   odoo_online=fin.get("odoo_online", False))
        return

    # Write briefing file
    today_str    = now.strftime("%Y-%m-%d")
    briefing_path = BRIEFINGS / f"Briefing_{today_str}.md"
    briefing_path.write_text(briefing_md, encoding="utf-8")
    print(f"\nBriefing written → {briefing_path}")

    log_action("briefing_generated", "ceo-briefing", "success",
               output_file=str(briefing_path),
               tasks_completed=vault_data["total"],
               bottlenecks=len(vault_data["bottlenecks"]),
               week_revenue=fin.get("week_revenue", 0.0),
               odoo_online=fin.get("odoo_online", False),
               task_id=task_id or "scheduled")

    update_dashboard(
        f"Briefing generated for {today_str} "
        f"({vault_data['total']} tasks, "
        f"{_fmt(fin.get('week_revenue', 0.0))} revenue)",
        "Success",
    )


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CEO Briefing Skill")
    parser.add_argument("--days",    type=int, default=7,
                        help="Look-back window in days (default: 7)")
    parser.add_argument("--task-id", default=None,
                        help="Source task ID (for audit logging)")
    args = parser.parse_args()
    run(days=args.days, task_id=args.task_id)
