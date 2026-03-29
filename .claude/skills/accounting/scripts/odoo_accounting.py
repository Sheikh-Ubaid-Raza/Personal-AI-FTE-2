"""
AI Employee — Odoo Accounting Skill (Action Layer)
Interfaces with Odoo 19 Community Edition via the JSON-RPC API.
HITL gate: only invoked after human ticks [x] in the Plan file.

Supported actions (set `action:` in task frontmatter):
  draft_invoice        — Create a DRAFT customer invoice in Odoo
  post_invoice         — Confirm/post a draft invoice (legally binding)
  fetch_payment_status — Pull AR status and write Financial_Summary.md

Usage:
    python odoo_accounting.py --task-id TASK_20260301T120000.md
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────
VAULT             = Path(__file__).resolve().parent.parent.parent.parent.parent
NEEDS_APPROVAL    = VAULT / "Needs_Approval"
NEEDS_ACTION      = VAULT / "Needs_Action"
DONE              = VAULT / "Done"
LOGS              = VAULT / "Logs"
DASHBOARD         = VAULT / "Dashboard.md"
FINANCIAL_SUMMARY = VAULT / "Financial_Summary.md"

load_dotenv(VAULT / ".env")

# ── Config ───────────────────────────────────────────────────────────
ODOO_URL      = os.getenv("ODOO_URL",      "http://localhost:8069").rstrip("/")
ODOO_DB       = os.getenv("ODOO_DB",       "")
ODOO_USER     = os.getenv("ODOO_USER",     "")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "")
DRY_RUN       = os.getenv("DRY_RUN",       "false").lower() == "true"

SUPPORTED_ACTIONS = {"draft_invoice", "post_invoice", "fetch_payment_status"}


# ── Logging ──────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "actor":       "accounting-skill",
        "action_type": action_type,
        "target":      target,
        "result":      result,
    }
    entry.update(extra)
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Dashboard Update ─────────────────────────────────────────────────

def update_dashboard(status: str, description: str, task_id: str) -> None:
    if not DASHBOARD.exists():
        return
    text = DASHBOARD.read_text(encoding="utf-8")
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    row  = f"| {ts} | Odoo: {description} — {task_id} | {status} |"
    marker = "| -------------------- | ---------------------------------------------------------- | ------- |"
    if marker in text:
        text = text.replace(marker, marker + "\n" + row)
        DASHBOARD.write_text(text, encoding="utf-8")


# ── Frontmatter Parser ───────────────────────────────────────────────

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


# ── Task Locator ─────────────────────────────────────────────────────

def find_task_file(task_id: str) -> Path | None:
    name = task_id if task_id.endswith(".md") else task_id + ".md"
    for folder in (NEEDS_APPROVAL, NEEDS_ACTION, DONE):
        candidate = folder / name
        if candidate.exists():
            return candidate
    return None


# ── Odoo JSON-RPC Client ─────────────────────────────────────────────

_uid: int | None = None


def _jsonrpc(service: str, method: str, args: list) -> object:
    """Low-level JSON-RPC call to Odoo's /web/jsonrpc endpoint."""
    payload = {
        "jsonrpc": "2.0",
        "method":  "call",
        "id":      1,
        "params":  {"service": service, "method": method, "args": args},
    }
    resp = requests.post(f"{ODOO_URL}/jsonrpc", json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        msg = (
            (data["error"].get("data") or {}).get("message")
            or data["error"].get("message", str(data["error"]))
        )
        raise RuntimeError(f"Odoo RPC error: {msg}")
    return data["result"]


def authenticate() -> int:
    global _uid
    if _uid is None:
        uid = _jsonrpc("common", "authenticate",
                       [ODOO_DB, ODOO_USER, ODOO_PASSWORD, {}])
        if not uid:
            raise RuntimeError(
                "Odoo authentication failed — verify ODOO_DB / ODOO_USER / ODOO_PASSWORD in .env"
            )
        _uid = uid
    return _uid


def odoo(model: str, method: str,
         args: list | None = None,
         kwargs: dict | None = None) -> object:
    """Authenticated execute_kw shorthand."""
    uid = authenticate()
    return _jsonrpc("object", "execute_kw",
                    [ODOO_DB, uid, ODOO_PASSWORD, model, method,
                     args or [], kwargs or {}])


def _fmt(amount: float) -> str:
    return f"${amount:,.2f}"


# ── Action: draft_invoice ────────────────────────────────────────────

def action_draft_invoice(fm: dict, task_id: str) -> tuple[bool, str]:
    """Create a DRAFT customer invoice in Odoo (does not post it)."""
    partner_name  = fm.get("partner", fm.get("customer", "")).strip()
    description   = fm.get("description", "Services").strip()
    amount_str    = fm.get("amount", "0").strip()
    invoice_date  = fm.get("invoice_date", "").strip()
    due_date      = fm.get("due_date", "").strip()
    currency_code = fm.get("currency_code", "").strip().upper()

    if not partner_name:
        return False, "Missing 'partner:' in task frontmatter."
    try:
        amount = float(amount_str)
    except ValueError:
        return False, f"Invalid amount value: '{amount_str}'"
    if amount <= 0:
        return False, f"Amount must be greater than 0, got {amount}"

    if DRY_RUN:
        msg = (
            f"[DRY RUN] Would create draft invoice:\n"
            f"  Partner     : {partner_name}\n"
            f"  Description : {description}\n"
            f"  Amount      : {_fmt(amount)}"
        )
        print(msg)
        log_action("draft_invoice", "odoo", "dry_run",
                   partner=partner_name, amount=amount, task_id=task_id)
        return True, msg

    # Look up partner
    partners = odoo("res.partner", "search_read",
        [[["name", "ilike", partner_name]]],
        {"fields": ["id", "name"], "limit": 1},
    )
    if not partners:
        return False, (
            f"Customer '{partner_name}' not found in Odoo.\n"
            f"Create them first at {ODOO_URL}/odoo/contacts."
        )
    partner = partners[0]

    # Build invoice values
    vals: dict = {
        "move_type":  "out_invoice",
        "partner_id": partner["id"],
        "invoice_line_ids": [(0, 0, {
            "name":       description,
            "quantity":   1.0,
            "price_unit": amount,
        })],
    }
    if invoice_date:
        vals["invoice_date"] = invoice_date
    if due_date:
        vals["invoice_date_due"] = due_date
    if currency_code:
        currencies = odoo("res.currency", "search_read",
            [[["name", "=", currency_code]]],
            {"fields": ["id"], "limit": 1},
        )
        if currencies:
            vals["currency_id"] = currencies[0]["id"]

    invoice_id = odoo("account.move", "create", [[vals]])

    # Read back to confirm
    created = odoo("account.move", "read",
        [[invoice_id] if isinstance(invoice_id, int) else invoice_id],
        {"fields": ["name", "amount_total"]},
    )
    ref   = created[0]["name"]        if created else str(invoice_id)
    total = created[0]["amount_total"] if created else amount

    log_action("draft_invoice", "odoo", "success",
               invoice_ref=ref, partner=partner["name"],
               amount=total, task_id=task_id)
    update_dashboard(
        "Success",
        f"Draft invoice {ref} for {partner['name']} ({_fmt(total)})",
        task_id,
    )
    return True, (
        f"  OK  Draft invoice created in Odoo\n"
        f"      Reference : {ref}\n"
        f"      Partner   : {partner['name']}\n"
        f"      Amount    : {_fmt(total)}\n"
        f"      Status    : DRAFT — review in Odoo before posting\n"
        f"      Odoo URL  : {ODOO_URL}/odoo/accounting/customer-invoices"
    )


# ── Action: post_invoice ─────────────────────────────────────────────

def action_post_invoice(fm: dict, task_id: str) -> tuple[bool, str]:
    """Confirm/post a draft invoice — makes it official and legally binding."""
    invoice_ref = fm.get("invoice_ref", fm.get("invoice", "")).strip()
    if not invoice_ref:
        return False, (
            "Missing 'invoice_ref:' in task frontmatter.\n"
            "Example: invoice_ref: INV/2026/00001"
        )

    if DRY_RUN:
        msg = f"[DRY RUN] Would post invoice: {invoice_ref}"
        print(msg)
        log_action("post_invoice", "odoo", "dry_run",
                   invoice_ref=invoice_ref, task_id=task_id)
        return True, msg

    records = odoo("account.move", "search_read",
        [[["name", "=", invoice_ref]]],
        {"fields": ["id", "state", "amount_total", "partner_id"]},
    )
    if not records:
        return False, f"Invoice '{invoice_ref}' not found in Odoo."

    inv = records[0]
    if inv["state"] == "posted":
        return True, f"Invoice {invoice_ref} is already posted — nothing to do."
    if inv["state"] != "draft":
        return False, (
            f"Invoice {invoice_ref} is in state '{inv['state']}'.\n"
            f"Only 'draft' invoices can be posted."
        )

    odoo("account.move", "action_post", [[inv["id"]]])

    partner_name = inv["partner_id"][1] if inv["partner_id"] else "unknown"
    log_action("post_invoice", "odoo", "success",
               invoice_ref=invoice_ref, partner=partner_name,
               amount=inv["amount_total"], task_id=task_id)
    update_dashboard(
        "Success",
        f"Posted invoice {invoice_ref} ({partner_name}, {_fmt(inv['amount_total'])})",
        task_id,
    )
    return True, (
        f"  OK  Invoice posted\n"
        f"      Reference : {invoice_ref}\n"
        f"      Partner   : {partner_name}\n"
        f"      Amount    : {_fmt(inv['amount_total'])}\n"
        f"      Status    : POSTED — awaiting payment"
    )


# ── Action: fetch_payment_status ─────────────────────────────────────

def action_fetch_payment_status(fm: dict, task_id: str) -> tuple[bool, str]:
    """Fetch AR payment status from Odoo and write Financial_Summary.md."""
    if DRY_RUN:
        msg = "[DRY RUN] Would fetch payment status from Odoo and write Financial_Summary.md"
        print(msg)
        log_action("fetch_payment_status", "odoo", "dry_run", task_id=task_id)
        return True, msg

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ts        = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Fetch all posted customer invoices
    invoices = odoo("account.move", "search_read",
        [[["move_type", "=", "out_invoice"], ["state", "=", "posted"]]],
        {"fields": ["name", "partner_id", "invoice_date_due",
                    "amount_total", "amount_residual", "payment_state"]},
    )

    # Aggregate by payment state
    buckets: dict[str, dict] = {}
    overdue_list: list[dict] = []
    for inv in invoices:
        st = inv["payment_state"]
        buckets.setdefault(st, {"count": 0, "total": 0.0, "residual": 0.0})
        buckets[st]["count"]    += 1
        buckets[st]["total"]    += inv["amount_total"]
        buckets[st]["residual"] += inv["amount_residual"]
        due = inv.get("invoice_date_due") or ""
        if due and due < today_str and st not in ("paid", "reversed"):
            overdue_list.append(inv)

    total_outstanding = sum(
        b["residual"] for s, b in buckets.items()
        if s not in ("paid", "reversed")
    )
    total_overdue = sum(i["amount_residual"] for i in overdue_list)

    # State labels for readability
    state_labels = {
        "not_paid":   "Not Paid",
        "in_payment": "In Payment",
        "paid":       "Paid",
        "partial":    "Partial",
        "reversed":   "Reversed / Credit",
    }

    # Build Financial_Summary.md
    md: list[str] = [
        "# Financial Summary — Accounts Receivable",
        f"*Last updated: {ts}  |  Source: {ODOO_URL}*",
        "",
        "## Payment Status Breakdown",
        "",
        f"| {'Status':<18} | {'Count':>5} | {'Invoiced':>14} | {'Outstanding':>12} |",
        f"| {'-'*18} | {'-'*5} | {'-'*14} | {'-'*12} |",
    ]
    for st, d in sorted(buckets.items()):
        label = state_labels.get(st, st)
        md.append(
            f"| {label:<18} | {d['count']:>5} |"
            f" {_fmt(d['total']):>14} | {_fmt(d['residual']):>12} |"
        )
    md += [
        "",
        f"**Total Outstanding : {_fmt(total_outstanding)}**",
        f"**Total Overdue     : {_fmt(total_overdue)}**",
        "",
    ]

    if overdue_list:
        md += [
            f"## Overdue Invoices ({len(overdue_list)})",
            "",
            f"| {'Reference':<20} | {'Partner':<26} | {'Due Date':<12} | {'Amount Due':>12} |",
            f"| {'-'*20} | {'-'*26} | {'-'*12} | {'-'*12} |",
        ]
        for inv in sorted(overdue_list, key=lambda x: x.get("invoice_date_due", "")):
            partner = (inv["partner_id"][1] if inv["partner_id"] else "-")[:25]
            md.append(
                f"| {inv['name']:<20} | {partner:<26}"
                f" | {inv.get('invoice_date_due', '-'):<12}"
                f" | {_fmt(inv['amount_residual']):>12} |"
            )
    else:
        md.append("## No Overdue Invoices")

    md += ["", "---", f"*Generated by AI Employee accounting skill*"]
    FINANCIAL_SUMMARY.write_text("\n".join(md), encoding="utf-8")

    log_action("fetch_payment_status", "odoo", "success",
               invoice_count=len(invoices),
               total_outstanding=total_outstanding,
               total_overdue=total_overdue,
               task_id=task_id)
    update_dashboard(
        "Success",
        f"Payment status: {len(invoices)} invoices, {_fmt(total_outstanding)} outstanding",
        task_id,
    )
    return True, (
        f"  OK  Payment status fetched from Odoo\n"
        f"      Invoices    : {len(invoices)}\n"
        f"      Outstanding : {_fmt(total_outstanding)}\n"
        f"      Overdue     : {_fmt(total_overdue)} ({len(overdue_list)} invoice(s))\n"
        f"      Written to  : Financial_Summary.md"
    )


# ── Main Execution ────────────────────────────────────────────────────

def execute(task_id: str | None = None) -> None:
    DONE.mkdir(parents=True, exist_ok=True)

    if not task_id:
        log_action("execution_error", "odoo", "no task_id provided")
        print("ERROR: --task-id is required")
        return

    log_action("skill_invoked", task_id, "started",
               mode="dry_run" if DRY_RUN else "live")

    # Validate credentials before doing anything
    if not DRY_RUN:
        missing = [k for k in ("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASSWORD")
                   if not os.getenv(k)]
        if missing:
            log_action("validation_error", task_id,
                       f"missing_env: {', '.join(missing)}")
            print(f"ERROR: Missing .env variables: {', '.join(missing)}")
            sys.exit(1)

    task_path = find_task_file(task_id)
    if not task_path:
        log_action("task_not_found", task_id, "failed")
        print(f"ERROR: Could not find task file for {task_id}")
        return

    text = task_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)

    # If action is not in the top-level frontmatter, search the body for an
    # embedded YAML block (created when watcher wraps Inbox files in ## Full Content)
    if not fm.get("action"):
        for embedded in re.finditer(r"---\s*\n(.*?)\n---", body, re.DOTALL):
            embedded_fm: dict = {}
            for line in embedded.group(1).split("\n"):
                line = line.strip()
                if not line or ":" not in line:
                    continue
                idx = line.index(":")
                embedded_fm[line[:idx].strip()] = line[idx + 1:].strip().strip('"').strip("'")
            if embedded_fm.get("action"):
                fm.update({k: v for k, v in embedded_fm.items() if k not in fm})
                break

    action = fm.get("action", "").lower().strip()
    if action not in SUPPORTED_ACTIONS:
        log_action("validation_error", task_id, f"unknown_action: {action}")
        print(
            f"ERROR: Unknown action '{action}'.\n"
            f"Supported: {', '.join(sorted(SUPPORTED_ACTIONS))}\n"
            f"Set 'action: <name>' in the task frontmatter."
        )
        return

    action_fn = {
        "draft_invoice":        action_draft_invoice,
        "post_invoice":         action_post_invoice,
        "fetch_payment_status": action_fetch_payment_status,
    }[action]

    print(f"Executing Odoo action '{action}' from {task_id}...")
    success, message = action_fn(fm, task_id)
    print(message)
    if not success:
        log_action(action, "odoo", "failed", error=message, task_id=task_id)
        sys.exit(1)


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Odoo Accounting Skill")
    parser.add_argument("--task-id", default=None,
                        help="Task ID to process (e.g. TASK_20260301T120000.md)")
    args = parser.parse_args()
    execute(task_id=args.task_id)
