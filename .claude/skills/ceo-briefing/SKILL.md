# CEO Briefing — Intelligence Skill

## Description

Generates the weekly "Monday Morning CEO Briefing" by scanning the last 7 days of
completed tasks in `Done/`, querying Odoo 19 for revenue and invoice data via
JSON-RPC, and writing a structured report to `Briefings/Briefing_YYYY-MM-DD.md`.

This skill runs autonomously on a schedule (Sunday night via cron / Task Scheduler)
or can be triggered manually from any task file.

**Script:** `scripts/generate_briefing.py`

## Trigger

Run this skill when:
- A task has `skill: ceo-briefing` or `action: generate_briefing` in frontmatter
- The human has ticked `- [x] **Approve Action:**` in the Plan file
- OR it is invoked directly by a cron scheduler (no approval gate required for
  read-only report generation)

```bash
python scripts/generate_briefing.py
# or with explicit date range:
python scripts/generate_briefing.py --days 7
```

## Inputs

| Input         | Source                                    | Required |
|---------------|-------------------------------------------|----------|
| `Done/` folder | Vault filesystem — last 7 days of files  | Yes      |
| Odoo JSON-RPC | `ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_PASSWORD` in `.env` | Optional |

## Output

`Briefings/Briefing_YYYY-MM-DD.md` — following the hackathon CEO Briefing template:

- Executive Summary (1 sentence)
- Revenue section (this week vs MTD from Odoo)
- Completed Tasks (from Done/)
- Bottlenecks (tasks that sat in Needs_Action > 2 days)
- Proactive Suggestions (subscription cost flags from Odoo)
- Upcoming work

## Procedure

1. Scan `Done/` for files with `mtime` within the last `--days` days
2. Parse frontmatter: extract `skill`, `action`, `status`, `executed_at`
3. Authenticate with Odoo (gracefully skips if Odoo offline)
4. Fetch this week's posted invoices → compute total revenue
5. Fetch any overdue invoices → surface as proactive suggestions
6. Identify bottlenecks: tasks whose `created` → `executed_at` gap > 48 h
7. Write `Briefings/Briefing_YYYY-MM-DD.md`
8. Log to `Logs/YYYY-MM-DD.json`
9. Update `Dashboard.md` Recent Activity

## Constraints

- **Read-only** — this skill never writes to Odoo or sends external messages
- **Odoo optional** — if Odoo is offline, financial section shows "Odoo Offline"
- **DRY_RUN=true** → prints report to stdout, does not write file
- **Credentials:** all Odoo config from `.env` — never hardcoded

## Credentials (`.env`)

```
ODOO_URL=http://localhost:8069
ODOO_DB=your_odoo_database_name
ODOO_USER=admin
ODOO_PASSWORD=your_odoo_password
```
