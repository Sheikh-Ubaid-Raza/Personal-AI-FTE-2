"""
AI Employee — Odoo MCP Server
Gives Claude Code direct read access to Odoo 19 Community Edition
via the JSON-RPC API.  All credentials are loaded from the vault .env.

Exposed tools (read + draft only — posting/confirming goes through HITL):
  odoo_test_connection      — verify connectivity and credentials
  odoo_list_invoices        — list invoices with optional status filter
  odoo_get_invoice          — full detail for one invoice by reference
  odoo_get_financial_summary — AR/AP summary: paid / partial / overdue
  odoo_list_customers       — search customers/partners
  odoo_create_draft_invoice — create a DRAFT invoice (does NOT post it)

Usage (stdio transport — launched by Claude Code via .mcp.json):
    python server.py
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ── Paths & Config ────────────────────────────────────────────────────
VAULT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(VAULT / ".env")

ODOO_URL      = os.getenv("ODOO_URL",      "http://localhost:8069").rstrip("/")
ODOO_DB       = os.getenv("ODOO_DB",       "")
ODOO_USER     = os.getenv("ODOO_USER",     "")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "")

mcp = FastMCP("odoo-accounting")

# ── JSON-RPC Helpers ──────────────────────────────────────────────────

_uid_cache: dict = {}


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


def _authenticate() -> int:
    key = (ODOO_URL, ODOO_DB, ODOO_USER)
    if key not in _uid_cache:
        uid = _jsonrpc("common", "authenticate",
                       [ODOO_DB, ODOO_USER, ODOO_PASSWORD, {}])
        if not uid:
            raise RuntimeError(
                "Odoo authentication failed — check ODOO_DB / ODOO_USER / ODOO_PASSWORD in .env"
            )
        _uid_cache[key] = uid
    return _uid_cache[key]


def _execute(model: str, method: str,
             args: list | None = None,
             kwargs: dict | None = None) -> object:
    uid = _authenticate()
    return _jsonrpc("object", "execute_kw",
                    [ODOO_DB, uid, ODOO_PASSWORD, model, method,
                     args or [], kwargs or {}])


def _fmt(amount: float) -> str:
    return f"${amount:,.2f}"


# ── Tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def odoo_test_connection() -> str:
    """
    Test connectivity to the Odoo instance and verify credentials.
    Returns server version, database name, and authenticated user UID.
    """
    try:
        version = _jsonrpc("common", "version", [])
        uid = _authenticate()
        return (
            f"Connected to Odoo {version.get('server_version', '?')}\n"
            f"  Database : {ODOO_DB}\n"
            f"  User     : {ODOO_USER}  (UID {uid})\n"
            f"  URL      : {ODOO_URL}"
        )
    except Exception as exc:
        return f"Connection failed: {exc}"


@mcp.tool()
def odoo_list_invoices(
    payment_state: str = "all",
    move_type: str = "out_invoice",
    limit: int = 25,
) -> str:
    """
    List invoices from Odoo with optional filters.

    Args:
        payment_state: 'all' | 'not_paid' | 'in_payment' | 'paid' | 'partial' | 'reversed'
        move_type: 'out_invoice' (customer) | 'in_invoice' (vendor)
        limit: max rows to return (default 25)
    """
    try:
        domain: list = [["move_type", "=", move_type], ["state", "=", "posted"]]
        if payment_state != "all":
            domain.append(["payment_state", "=", payment_state])

        invoices = _execute("account.move", "search_read",
            [domain],
            {
                "fields": ["name", "partner_id", "invoice_date_due",
                           "amount_total", "amount_residual", "payment_state"],
                "order":  "invoice_date_due asc",
                "limit":  limit,
            },
        )

        if not invoices:
            return "No invoices found matching the filter."

        today = datetime.now(timezone.utc).date()
        header = (
            f"{'Reference':<20} {'Partner':<26} {'Due':<12}"
            f" {'Total':>10} {'Residual':>10} Status"
        )
        rows = [header, "-" * 90]

        for inv in invoices:
            due = inv.get("invoice_date_due") or "-"
            overdue_flag = ""
            if due != "-":
                from datetime import date
                due_d = date.fromisoformat(due)
                if due_d < today and inv["payment_state"] not in ("paid", "reversed"):
                    overdue_flag = " !"

            partner = (inv["partner_id"][1] if inv["partner_id"] else "-")[:25]
            rows.append(
                f"{inv['name']:<20} {partner:<26} {due:<12}"
                f" {_fmt(inv['amount_total']):>10}"
                f" {_fmt(inv['amount_residual']):>10}"
                f" {inv['payment_state']}{overdue_flag}"
            )

        return "\n".join(rows)
    except Exception as exc:
        return f"Error fetching invoices: {exc}"


@mcp.tool()
def odoo_get_invoice(invoice_name: str) -> str:
    """
    Get full details of a single invoice by its reference number.

    Args:
        invoice_name: Invoice reference, e.g. 'INV/2026/00001'
    """
    try:
        records = _execute("account.move", "search_read",
            [[["name", "=", invoice_name]]],
            {
                "fields": [
                    "name", "partner_id", "invoice_date", "invoice_date_due",
                    "amount_untaxed", "amount_tax", "amount_total",
                    "amount_residual", "payment_state", "state",
                    "invoice_line_ids", "ref",
                ],
            },
        )
        if not records:
            return f"Invoice '{invoice_name}' not found in Odoo."

        inv = records[0]
        lines_data = _execute("account.move.line", "search_read",
            [[
                ["move_id", "=", inv["id"]],
                ["display_type", "not in", ["line_section", "line_note"]],
            ]],
            {"fields": ["name", "quantity", "price_unit", "price_subtotal"]},
        )

        out = [
            f"Invoice  : {inv['name']}",
            f"Partner  : {inv['partner_id'][1] if inv['partner_id'] else '-'}",
            f"Date     : {inv.get('invoice_date', '-')}",
            f"Due      : {inv.get('invoice_date_due', '-')}",
            f"State    : {inv['state']} / {inv['payment_state']}",
            "",
            f"{'Description':<40} {'Qty':>6} {'Unit Price':>12} {'Subtotal':>12}",
            "-" * 74,
        ]
        for line in lines_data:
            out.append(
                f"{str(line['name'])[:39]:<40}"
                f" {line['quantity']:>6.2f}"
                f" {_fmt(line['price_unit']):>12}"
                f" {_fmt(line['price_subtotal']):>12}"
            )
        out += [
            "-" * 74,
            f"{'Subtotal':>60} {_fmt(inv['amount_untaxed']):>12}",
            f"{'Tax':>60} {_fmt(inv['amount_tax']):>12}",
            f"{'TOTAL':>60} {_fmt(inv['amount_total']):>12}",
            f"{'Amount Due':>60} {_fmt(inv['amount_residual']):>12}",
        ]
        return "\n".join(out)
    except Exception as exc:
        return f"Error fetching invoice: {exc}"


@mcp.tool()
def odoo_get_financial_summary() -> str:
    """
    Return an AR and AP financial summary grouped by payment state,
    including total outstanding and overdue amounts.
    """
    try:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        def _section(move_type: str, label: str) -> list[str]:
            invoices = _execute("account.move", "search_read",
                [[["move_type", "=", move_type], ["state", "=", "posted"]]],
                {"fields": ["amount_total", "amount_residual",
                            "payment_state", "invoice_date_due"]},
            )
            buckets: dict[str, dict] = {}
            overdue = 0.0
            for inv in invoices:
                st = inv["payment_state"]
                buckets.setdefault(st, {"count": 0, "residual": 0.0})
                buckets[st]["count"]    += 1
                buckets[st]["residual"] += inv["amount_residual"]
                due = inv.get("invoice_date_due") or ""
                if due and due < today_str and st not in ("paid", "reversed"):
                    overdue += inv["amount_residual"]

            outstanding = sum(
                b["residual"] for s, b in buckets.items()
                if s not in ("paid", "reversed")
            )
            rows = [
                f"\n## {label}",
                f"| {'Status':<14} | {'Count':>5} | {'Outstanding':>12} |",
                f"| {'-'*14} | {'-'*5} | {'-'*12} |",
            ]
            for st, d in sorted(buckets.items()):
                rows.append(f"| {st:<14} | {d['count']:>5} | {_fmt(d['residual']):>12} |")
            rows += [
                f"\nTotal Outstanding : {_fmt(outstanding)}",
                f"Total Overdue     : {_fmt(overdue)}",
            ]
            return rows

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        out = [f"# Odoo Financial Summary — {ts}"]
        out.extend(_section("out_invoice", "Accounts Receivable (AR — Customer Invoices)"))
        out.extend(_section("in_invoice",  "Accounts Payable   (AP — Vendor Bills)"))
        return "\n".join(out)
    except Exception as exc:
        return f"Error building financial summary: {exc}"


@mcp.tool()
def odoo_list_customers(search: str = "", limit: int = 20) -> str:
    """
    List customers/partners from Odoo.

    Args:
        search: optional name substring filter (case-insensitive)
        limit: max rows (default 20)
    """
    try:
        domain: list = [["customer_rank", ">", 0]]
        if search:
            domain.append(["name", "ilike", search])

        partners = _execute("res.partner", "search_read",
            [domain],
            {"fields": ["name", "email", "phone", "country_id"], "limit": limit},
        )
        if not partners:
            return "No customers found."

        rows = [
            f"{'Name':<30} {'Email':<30} {'Phone':<16} Country",
            "-" * 90,
        ]
        for p in partners:
            country = p["country_id"][1] if p.get("country_id") else "-"
            rows.append(
                f"{p['name'][:29]:<30}"
                f" {(p.get('email') or '-')[:29]:<30}"
                f" {(p.get('phone') or '-')[:15]:<16}"
                f" {country}"
            )
        return "\n".join(rows)
    except Exception as exc:
        return f"Error listing customers: {exc}"


@mcp.tool()
def odoo_create_draft_invoice(
    partner_name: str,
    description: str,
    amount: float,
    invoice_date: str = "",
    due_date: str = "",
    currency_code: str = "",
) -> str:
    """
    Create a DRAFT customer invoice in Odoo.
    The invoice is NOT posted/confirmed — a human must approve via the
    accounting skill HITL gate or manually in the Odoo UI.

    Args:
        partner_name:  Customer name (exact or close match)
        description:   Line item description
        amount:        Line amount excluding tax
        invoice_date:  YYYY-MM-DD (default: today)
        due_date:      YYYY-MM-DD (optional)
        currency_code: e.g. 'USD', 'EUR' (uses Odoo company default if blank)
    """
    try:
        partners = _execute("res.partner", "search_read",
            [[["name", "ilike", partner_name]]],
            {"fields": ["id", "name"], "limit": 1},
        )
        if not partners:
            return (
                f"Partner '{partner_name}' not found. "
                f"Create the customer in Odoo first."
            )
        partner = partners[0]

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
            currencies = _execute("res.currency", "search_read",
                [[["name", "=", currency_code.upper()]]],
                {"fields": ["id"], "limit": 1},
            )
            if currencies:
                vals["currency_id"] = currencies[0]["id"]

        invoice_id = _execute("account.move", "create", [[vals]])
        created = _execute("account.move", "read",
            [[invoice_id] if isinstance(invoice_id, int) else invoice_id],
            {"fields": ["name", "amount_total"]},
        )
        ref   = created[0]["name"]   if created else str(invoice_id)
        total = created[0]["amount_total"] if created else amount

        return (
            f"Draft invoice created in Odoo\n"
            f"  Reference : {ref}\n"
            f"  Partner   : {partner['name']}\n"
            f"  Amount    : {_fmt(total)}\n"
            f"  Status    : DRAFT — not posted\n"
            f"  Next step : Approve via accounting skill or post manually in Odoo UI."
        )
    except Exception as exc:
        return f"Error creating draft invoice: {exc}"


# ── Entry Point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
