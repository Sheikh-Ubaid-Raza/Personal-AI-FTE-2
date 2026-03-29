# Task Planner — Reasoning Loop

## Description

Before executing any task, the AI Employee must **think first**. This skill generates a structured plan file (`Plan_<timestamp>.md`) for every incoming task, ensuring no action is taken without deliberate reasoning, risk assessment, and — where required — human approval.

This is the **Silver Tier** upgrade: the AI Employee stops being reactive and starts being deliberate.

## Trigger

Run this skill automatically during orchestrator triage whenever a `TASK_*.md` file in `Needs_Action/` has `status: pending_triage`.

## Procedure

### STEP 1 — Read the Task

1. Parse the YAML frontmatter and body of the `TASK_*.md` file.
2. Extract: `original_file`, `source`, `created`, and the full body content.
3. Determine the task summary (first meaningful line of the body, max 120 chars).

### STEP 2 — Classify (reuse file-triage rules)

Apply the same classification from the `file-triage` skill:

| Category        | Keywords                                                             | Priority |
|-----------------|----------------------------------------------------------------------|----------|
| **Urgent**      | `urgent`, `asap`, `deadline`, `overdue`, `critical`, `immediately`   | high     |
| **Actionable**  | `invoice`, `reply`, `report`, `payment`, `schedule`, `send`, `create`| medium   |
| **Informational** | Everything else                                                    | low      |

### STEP 3 — Assess Risk Level

Determine risk by cross-referencing the task content against the Company Handbook's approval boundaries:

| Risk Level | Criteria |
|------------|----------|
| **High**   | Task involves actions requiring human approval: sending emails, making payments, posting to social media, contacting new people. OR task is classified as Urgent. |
| **Medium** | Task is Actionable but does not involve approval-boundary actions. |
| **Low**    | Task is Informational, or involves only auto-approvable actions (reading files, creating summaries, writing logs). |

### STEP 4 — Safety Check

Determine whether human approval is required before execution:

- **Yes** — if Risk Level is High, OR the task explicitly mentions external communication, financial transactions, or irreversible operations.
- **No** — if the task only involves internal, reversible, read-only, or logging actions.

### STEP 5 — Generate Step-by-Step Plan

Build a numbered action plan based on the task content and category:

1. Always start with: "Read and analyze the source material"
2. Add category-specific steps derived from detected keywords:
   - `invoice/payment` → "Prepare financial document", "Verify amounts and recipients"
   - `reply/send` → "Draft response/message", "Review tone and content"
   - `report` → "Gather relevant data", "Compile report"
   - `schedule` → "Check calendar availability", "Create schedule entry"
   - `create` → "Define requirements", "Create the deliverable"
   - Urgent tasks → Prepend "PRIORITY: Assess situation immediately"
3. If Safety Check = Yes, add: "Submit for human approval before proceeding"
4. Always end with: "Log completion to Logs/"

### STEP 6 — Write Plan File

Create `Needs_Action/Plan_<YYYYMMDDTHHMMSS>.md` with this exact schema:

```markdown
---
type: plan
source_task: <TASK filename>
created: <ISO-8601 timestamp>
status: pending_review
risk_level: <low|medium|high>
needs_approval: <yes|no>
---

## Original Task

<First meaningful line from the task body — max 120 characters>

## Objective

<One clear, imperative sentence describing what must be done. Prefix "URGENT:" for urgent tasks.>

## Step-by-Step Plan

1. <Step 1>
2. <Step 2>
...

## Safety Check

**Needs Human Approval:** <Yes/No>
**Reason:** <Why or why not>

## Risk Level

**Level:** <Low/Medium/High>
**Factors:** <Brief explanation of what drove the risk assessment>

## FINAL APPROVAL GATE

- [ ] **Approve Action:** Tick this box to authorize the AI Employee to execute this task.
```

> **Note:** For plans with `needs_approval: no`, the checkbox is pre-ticked:
> ```markdown
> ## FINAL APPROVAL GATE
>
> - [x] **Approve Action:** Auto-approved — low-risk, internal-only task.
> ```

### STEP 7 — Checkbox Approval Gate

The orchestrator scans `Needs_Approval/` each cycle for Plan files where the user has ticked the approval checkbox:

1. If `- [x] **Approve Action:**` is found → execute the associated skill and move plan + task to `Done/`.
2. If `- [ ] **Approve Action:**` is found → skip (awaiting human approval).
3. If the `## FINAL APPROVAL GATE` section is missing entirely → quarantine the file (move to `Done/` with `status: quarantined`).

### STEP 8 — Link Plan to Task

Update the original `TASK_*.md` frontmatter:
- Add `plan_file: <Plan filename>`
- Set `status` to the triage category (`urgent`, `actionable`, `informational`)

### STEP 9 — Log

Append a JSON-lines entry to `Logs/<YYYY-MM-DD>.json`:

```json
{
  "timestamp": "<ISO-8601>",
  "actor": "task-planner",
  "action_type": "plan_generated",
  "target": "<Plan filename>",
  "source_task": "<TASK filename>",
  "risk_level": "<low|medium|high>",
  "needs_approval": "<yes|no>",
  "result": "success"
}
```

## Constraints

- **Think before acting** — A plan must exist before any task is executed.
- **Never execute** — This skill only generates plans. Execution is a separate concern.
- **Markdown only** — All output is `.md` files with YAML frontmatter.
- **No deletion** — Never delete files. Plans are permanent audit records.
- **Idempotent** — If a task already has a `plan_file` in its frontmatter, skip it.
- **Handbook compliance** — Risk and safety assessments must align with Company Handbook rules.

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

**Output** — `Needs_Action/Plan_20260215T090105.md`:

```markdown
---
type: plan
source_task: TASK_20260215T090000.md
created: 2026-02-15T09:01:05Z
status: pending_review
risk_level: medium
needs_approval: yes
---

## Original Task

Please prepare the Q1 invoice for Acme Corp. Total amount is $3,200 for consulting services.

## Objective

Prepare and send the Q1 2026 invoice for $3,200 to Acme Corp for consulting services.

## Step-by-Step Plan

1. Read and analyze the source material
2. Prepare financial document with correct amounts and line items
3. Verify amounts and recipients against existing records
4. Submit for human approval before proceeding
5. Log completion to Logs/

## Safety Check

**Needs Human Approval:** Yes
**Reason:** Task involves preparing a financial document (invoice) which may lead to a payment request — requires human verification of amounts and recipient.

## Risk Level

**Level:** Medium
**Factors:** Financial document preparation (invoice). No direct external communication but involves monetary amounts that require accuracy verification.
```
