# Odoo Accounting — External Action Skill

## Description

Interfaces with a local Odoo 19 Community Edition instance via the JSON-RPC API
to perform autonomous accounting actions.  Every action is gated behind the
HITL checkbox in the Plan file — the orchestrator will never execute this skill
until `- [x] **Approve Action:**` is ticked.

**Script:** `scripts/odoo_accounting.py`

## Trigger

Run this skill when a task requires an Odoo accounting action AND the human has
ticked `- [x] **Approve Action:**` in the corresponding Plan file.

```bash
python scripts/odoo_accounting.py --task-id TASK_20260301T120000.md
```

## Supported Actions

Set `action:` in the task frontmatter to one of:

| Action | What it does |
|---|---|
| `draft_invoice` | Create a DRAFT customer invoice in Odoo (does not post it) |
| `post_invoice` | Confirm/post an existing draft invoice (makes it legally binding) |
| `fetch_payment_status` | Pull AR status from Odoo and write `Financial_Summary.md` |

## Frontmatter Examples

### draft_invoice
```yaml
---
action: draft_invoice
skill: accounting
partner: "Acme Corp"
description: "Consulting services — March 2026"
amount: 1500.00
invoice_date: 2026-03-01
due_date: 2026-03-31
currency_code: USD
---
```

### post_invoice
```yaml
---
action: post_invoice
skill: accounting
invoice_ref: INV/2026/00001
---
```

### fetch_payment_status
```yaml
---
action: fetch_payment_status
skill: accounting
---
```

## Procedure

1. Orchestrator reads the Plan file — waits for `[x]` checkbox
2. `detect_skill()` returns `"accounting"` from the `action:` or `skill:` field
3. `run_skill("accounting", task_id)` calls this script via subprocess
4. Script authenticates with Odoo via JSON-RPC (`/web/jsonrpc`)
5. Executes the requested action:
   - **draft_invoice** → `account.move.create()` with `move_type=out_invoice`, state=draft
   - **post_invoice**  → `account.move.action_post()` on the target record
   - **fetch_payment_status** → `account.move.search_read()` + aggregation → writes `Financial_Summary.md`
6. Logs result to `Logs/YYYY-MM-DD.json`
7. Updates `Dashboard.md` Recent Activity table

## Constraints

- **Never execute without approval** — HITL checkbox must be ticked
- **Never hardcode credentials** — all config from `.env`
- **draft_invoice does NOT post** — always creates state=draft for human review
- **post_invoice is irreversible** — requires its own separate HITL-approved task
- **DRY_RUN=true** → logs intent, makes no Odoo changes
- **Timeout:** 60 s (network-only, no browser)

## Credentials (`.env`)

```
ODOO_URL=http://localhost:8069
ODOO_DB=your_odoo_database_name
ODOO_USER=admin
ODOO_PASSWORD=your_odoo_password
```

## MCP Server

An MCP server at `.claude/mcp-servers/odoo-mcp/server.py` gives Claude Code
direct read access to Odoo during interactive sessions (configured in `.mcp.json`).
It exposes read tools and `odoo_create_draft_invoice` — but never posts invoices.
