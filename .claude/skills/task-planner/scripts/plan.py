"""
AI Employee — Task Planner Skill (Standalone Script)
=====================================================
For every TASK_*.md in Needs_Action/ with status: pending_triage,
generates a structured Plan_<timestamp>.md in Needs_Approval/,
applies the HITL approval gate, and logs everything.

Usage:
    python plan.py [--task-id TASK_FILE.md] [--dry-run]

    --task-id  Process a single task file (name only, not full path)
               If omitted, processes ALL pending_triage tasks in Needs_Action/
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
VAULT          = Path(__file__).resolve().parent.parent.parent.parent.parent
NEEDS_ACTION   = VAULT / "Needs_Action"
NEEDS_APPROVAL = VAULT / "Needs_Approval"
DONE           = VAULT / "Done"
LOGS           = VAULT / "Logs"

# ── Classification Tables (mirrors file-triage rules) ─────────────────
URGENT_KEYWORDS = {
    "urgent", "asap", "deadline", "overdue", "critical", "immediately",
    "emergency", "priority", "action required",
}
ACTIONABLE_KEYWORDS = {
    "invoice", "reply", "report", "payment", "schedule", "send", "create",
    "prepare", "submit", "update", "respond", "call", "meeting", "review",
    "approve", "sign", "draft", "buy", "order", "fix", "resolve",
}

# High-risk keywords — triggers human approval requirement
HIGH_RISK_KEYWORDS = {
    "email", "invoice", "payment", "transfer", "post", "publish",
    "send", "contact", "linkedin", "facebook", "instagram", "twitter",
    "external", "client", "customer", "bank", "wire", "delete",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ts_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


# ── Logging ────────────────────────────────────────────────────────────

def log_event(target: str, source_task: str, risk_level: str,
              needs_approval: str, result: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp":      _now_iso(),
        "actor":          "task-planner",
        "action_type":    "plan_generated",
        "target":         target,
        "source_task":    source_task,
        "risk_level":     risk_level,
        "needs_approval": needs_approval,
        "result":         result,
    }
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


def write_frontmatter_str(fm: dict, body: str) -> str:
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(body.lstrip("\n"))
    return "\n".join(lines)


# ── Classification ─────────────────────────────────────────────────────

def classify(text: str) -> tuple[str, str, str, str]:
    """
    Returns (category, priority, risk_level, needs_approval).
    """
    lowered = text.lower()

    # Category
    if any(kw in lowered for kw in URGENT_KEYWORDS):
        category, priority = "urgent", "high"
    elif any(kw in lowered for kw in ACTIONABLE_KEYWORDS):
        category, priority = "actionable", "medium"
    else:
        category, priority = "informational", "low"

    # Risk
    is_high_risk = (
        category == "urgent"
        or any(kw in lowered for kw in HIGH_RISK_KEYWORDS)
    )
    risk_level     = "high" if is_high_risk else ("medium" if category == "actionable" else "low")
    needs_approval = "yes"  if risk_level in ("high", "medium") else "no"

    return category, priority, risk_level, needs_approval


def extract_summary(body: str, filename: str, max_len: int = 120) -> str:
    for line in body.split("\n"):
        stripped = line.strip().lstrip("#").strip()
        if stripped and stripped not in ("Task Summary", "Full Content", "Objective", "---"):
            return stripped[:max_len]
    return filename


# ── Plan Step Generator ────────────────────────────────────────────────

def generate_steps(category: str, needs_approval: str, task_text: str) -> list[str]:
    steps = ["Read and analyze the source material"]
    lowered = task_text.lower()

    if category == "urgent":
        steps.insert(0, "PRIORITY: Assess the situation immediately")

    if any(k in lowered for k in ("invoice", "payment", "financial", "amount")):
        steps += ["Prepare the financial document with correct amounts and line items",
                  "Verify amounts and recipients against existing records"]
    if any(k in lowered for k in ("email", "reply", "respond", "send")):
        steps += ["Draft the response / message", "Review tone, content, and recipients"]
    if any(k in lowered for k in ("report", "briefing", "summary")):
        steps += ["Gather all relevant data from Done/ and Logs/", "Compile the report"]
    if any(k in lowered for k in ("schedule", "meeting", "calendar")):
        steps += ["Check calendar availability", "Create the schedule entry"]
    if any(k in lowered for k in ("post", "linkedin", "facebook", "instagram", "twitter")):
        steps += ["Draft the social media content", "Verify image/attachment requirements",
                  "Select the correct platform skill"]
    if any(k in lowered for k in ("create", "draft", "build")):
        steps += ["Define requirements and deliverables", "Create the requested item"]

    if needs_approval == "yes":
        steps.append("Submit for human approval before proceeding (HITL gate)")

    steps.append("Log completion to Logs/")
    return steps


def generate_objective(category: str, summary: str) -> str:
    prefix = "URGENT: " if category == "urgent" else ""
    return f"{prefix}Execute the following task completely and correctly: {summary}"


def safety_reason(risk_level: str, needs_approval: str, task_text: str) -> tuple[str, str]:
    """Returns (needs_human_str, reason_str)."""
    if needs_approval == "no":
        return "No", "Task involves only internal, reversible, or read-only operations."
    lowered = task_text.lower()
    reasons = []
    if any(k in lowered for k in ("invoice", "payment")):
        reasons.append("financial document preparation requiring amount verification")
    if any(k in lowered for k in ("email", "send", "reply")):
        reasons.append("external communication")
    if any(k in lowered for k in ("post", "linkedin", "facebook", "instagram", "twitter")):
        reasons.append("social media publication (irreversible)")
    if not reasons:
        reasons.append("actionable task with external impact")
    return "Yes", f"Task involves: {', '.join(reasons)}."


# ── Plan File Renderer ─────────────────────────────────────────────────

def render_plan(source_task: str, summary: str, category: str,
                priority: str, risk_level: str, needs_approval: str,
                steps: list[str], task_text: str) -> str:
    ts           = _now_iso()
    steps_md     = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    objective    = generate_objective(category, summary)
    needs_human, reason = safety_reason(risk_level, needs_approval, task_text)

    if needs_approval == "no":
        gate = (
            "## FINAL APPROVAL GATE\n\n"
            "- [x] **Approve Action:** Auto-approved — low-risk, internal-only task."
        )
    else:
        gate = (
            "## FINAL APPROVAL GATE\n\n"
            "- [ ] **Approve Action:** Tick this box to authorize the AI Employee to execute this task."
        )

    return f"""---
type: plan
source_task: {source_task}
created: {ts}
status: pending_review
risk_level: {risk_level}
needs_approval: {needs_approval}
category: {category}
priority: {priority}
---

## Original Task

{summary}

## Objective

{objective}

## Step-by-Step Plan

{steps_md}

## Safety Check

**Needs Human Approval:** {needs_human}
**Reason:** {reason}

## Risk Level

**Level:** {risk_level.capitalize()}
**Factors:** Category={category}, priority={priority}. {"External/financial action detected." if risk_level == "high" else "Internal or low-impact action." if risk_level == "low" else "Actionable but limited external exposure."}

{gate}
"""


# ── Core: plan one task ────────────────────────────────────────────────

def plan_task(path: Path, dry_run: bool) -> dict | None:
    """
    Generate a Plan file for a single TASK_*.md.
    Returns summary dict on success, None if skipped.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"  [SKIP] {path.name}: read error — {exc}")
        return None

    fm, body = parse_frontmatter(raw)

    # Process pending_triage tasks, OR triaged tasks that have no plan yet
    TRIAGE_STATES = {"pending_triage", "urgent", "actionable", "informational"}
    if fm.get("status", "").strip() not in TRIAGE_STATES:
        return None

    # Skip if plan already generated (idempotent)
    if fm.get("plan_file"):
        print(f"  [SKIP] {path.name}: plan already exists ({fm['plan_file']})")
        return None

    category, priority, risk_level, needs_approval = classify(raw)
    summary = extract_summary(body, path.stem)
    steps   = generate_steps(category, needs_approval, raw)

    plan_name = f"Plan_{_ts_filename()}_{path.stem[-8:]}.md"
    plan_path = NEEDS_APPROVAL / plan_name

    plan_md = render_plan(
        source_task   = path.name,
        summary       = summary,
        category      = category,
        priority      = priority,
        risk_level    = risk_level,
        needs_approval= needs_approval,
        steps         = steps,
        task_text     = raw,
    )

    print(f"  {path.name}")
    print(f"    Category     : {category} | Priority: {priority} | Risk: {risk_level}")
    print(f"    HITL Required: {needs_approval}")
    print(f"    Plan file    : {plan_name}")

    if dry_run:
        print(f"\n  [DRY RUN] Plan preview:\n")
        print(plan_md[:800] + "…" if len(plan_md) > 800 else plan_md)
        return {"file": path.name, "plan": plan_name, "category": category}

    # Write plan
    NEEDS_APPROVAL.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(plan_md, encoding="utf-8")

    # Back-link plan in task frontmatter
    fm["plan_file"] = plan_name
    fm["status"]    = category  # e.g. actionable, urgent, informational
    fm["priority"]  = priority
    path.write_text(write_frontmatter_str(fm, body), encoding="utf-8")

    log_event(plan_name, path.name, risk_level, needs_approval, "success")

    return {"file": path.name, "plan": plan_name, "category": category, "risk": risk_level}


# ── Main ───────────────────────────────────────────────────────────────

def run(task_id: str | None = None, dry_run: bool = False) -> None:
    NEEDS_ACTION.mkdir(parents=True, exist_ok=True)
    NEEDS_APPROVAL.mkdir(parents=True, exist_ok=True)
    ts_start = _now_iso()

    print(f"\nTask Planner — {ts_start}")

    if task_id:
        candidates = []
        for folder in (NEEDS_ACTION, NEEDS_APPROVAL, DONE):
            candidate = folder / (task_id if task_id.endswith(".md") else task_id + ".md")
            if candidate.exists():
                candidates = [candidate]
                break
        if not candidates:
            print(f"ERROR: Task file not found: {task_id}")
            sys.exit(1)
    else:
        candidates = [
            p for p in sorted(NEEDS_ACTION.glob("TASK_*.md"))
        ]

    if not candidates:
        print("  No TASK_*.md files found in Needs_Action/.")
        return

    print(f"Found {len(candidates)} candidate task(s).")

    results = []
    for path in candidates:
        result = plan_task(path, dry_run)
        if result:
            results.append(result)

    if not results:
        print("\n  No tasks required planning (all already planned or not pending_triage).")
        return

    print(f"\nGenerated {len(results)} plan(s):")
    for r in results:
        icon = "🔴" if r["category"] == "urgent" else ("🟡" if r["category"] == "actionable" else "🔵")
        hitl = " [HITL required]" if r.get("risk") in ("high", "medium") else " [auto-approved]"
        print(f"  {icon} {r['plan']}{hitl}")

    if dry_run:
        print("\n[DRY RUN] — no files were modified.")
    else:
        print(f"\nPlans written to Needs_Approval/. Logs updated.")


# ── CLI ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task Planner Skill — AI Employee")
    parser.add_argument(
        "--task-id", default=None,
        help="Process a single task file (filename only, e.g. TASK_20260301T120000.md)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview plans without writing files",
    )
    args = parser.parse_args()
    run(task_id=args.task_id, dry_run=args.dry_run)
