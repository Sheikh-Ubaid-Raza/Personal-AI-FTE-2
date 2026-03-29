# File Triage & Intelligence

## Description

Analyzes incoming markdown tasks in the `Needs_Action/` folder, classifies them by urgency and type, updates the Dashboard, and enriches actionable items with a clear objective.

## Trigger

Run this skill whenever new `TASK_*.md` files appear in `Needs_Action/` with `status: pending_triage`.

## Procedure

### STEP 1 — Scan

1. Read every `.md` file inside `Needs_Action/`.
2. Filter to files whose YAML frontmatter contains `status: pending_triage`.
3. Collect a list of files to process. If the list is empty, stop and report "No tasks to triage."

### STEP 2 — Classify

For each file, read its full content and assign exactly one category:

| Category        | Criteria                                                                                   | Priority   |
|-----------------|--------------------------------------------------------------------------------------------|------------|
| **Urgent**      | Contains keywords: `urgent`, `asap`, `deadline`, `overdue`, `critical`, `immediately`      | high       |
| **Actionable**  | Requests a deliverable or response (invoice, reply, report, payment, schedule, send, create)| medium     |
| **Informational** | FYI, status update, newsletter, or notification with no required action                  | low        |

Apply rules top-down — first match wins.

### STEP 3 — Update Dashboard

Open `Dashboard.md` and **replace** the `## Active Tasks` table with a refreshed version containing every non-Done task. Each row must include:

| Column   | Source                            |
|----------|-----------------------------------|
| ID       | Sequential integer (1, 2, 3 …)   |
| Task     | First heading or first 60 chars   |
| Source   | `source` from frontmatter         |
| Priority | `high` / `medium` / `low`        |
| Status   | The newly assigned category       |
| Created  | `created` from frontmatter        |

Also append a line to the `## Recent Activity` table:

```
| <timestamp> | Triaged <filename> → <category> | Success |
```

### STEP 4 — Enrich Actionable & Urgent Tasks

For every file classified as **Actionable** or **Urgent**:

1. Update the YAML frontmatter:
   - Set `status` to the category name (e.g. `actionable`, `urgent`).
   - Set `priority` to the matching priority from the table above.
   - Add `triaged: <ISO-8601 timestamp>`.
2. Insert a new section immediately after `# Task Summary`:

```markdown
## Objective

<One clear, imperative sentence describing what must be done to resolve this task.>
```

For **Informational** files:

1. Update frontmatter: `status: informational`, `priority: low`, add `triaged` timestamp.
2. No objective is needed.

## Constraints

- **Markdown only** — Ignore any non-`.md` files in `Needs_Action/`.
- **No auto-completion** — Never move files to `Done/` without explicit human verification.
- **No deletion** — Never delete any file. Archive by moving to `Done/` only when instructed.
- **Idempotent** — If a file has already been triaged (`status` is not `pending_triage`), skip it.
- **Audit everything** — Append a JSON-lines entry to `Logs/<YYYY-MM-DD>.json` for each file triaged:

```json
{
  "timestamp": "<ISO-8601>",
  "actor": "file-triage-skill",
  "action_type": "triage",
  "target": "<filename>",
  "category": "<urgent|actionable|informational>",
  "result": "success"
}
```

## Example

**Input** — `Needs_Action/TASK_20260215T090000.md`:

```markdown
---
type: task_notification
source: Inbox
original_file: client_invoice.md
created: 2026-02-15T09:00:00Z
status: pending_triage
priority: medium
---

# Task Summary

Please prepare the Q1 invoice for Acme Corp. Total amount is $3,200 for consulting services.
```

**Output** — same file after triage:

```markdown
---
type: task_notification
source: Inbox
original_file: client_invoice.md
created: 2026-02-15T09:00:00Z
status: actionable
priority: medium
triaged: 2026-02-15T09:01:00Z
---

# Task Summary

Please prepare the Q1 invoice for Acme Corp. Total amount is $3,200 for consulting services.

## Objective

Generate and send the Q1 2026 invoice for $3,200 to Acme Corp.
```
