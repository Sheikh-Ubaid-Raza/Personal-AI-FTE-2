"""
AI Employee — Orchestrator (Decision Layer) [Gold Tier]
Scans Needs_Action/ for pending tasks, generates reasoning plans,
classifies them, enforces HITL approval gates, executes approved
skills, updates Dashboard.md, and moves completed tasks to Done/.

Gold Tier additions:
  • CEO Briefing skill routing
  • Graceful degradation: service health tracking with Dashboard alerts
  • Structured error classification (timeout / auth / connection)
  • Fixed: accounting skill now properly dispatched via run_skill()
"""

import json
import re
import signal
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.layout import Layout

# ── Paths ────────────────────────────────────────────────────────────
VAULT = Path(__file__).resolve().parent
NEEDS_ACTION = VAULT / "Needs_Action"
NEEDS_APPROVAL = VAULT / "Needs_Approval"
APPROVED = VAULT / "Approved"
DONE = VAULT / "Done"
LOGS = VAULT / "Logs"
DASHBOARD = VAULT / "Dashboard.md"

# Skill script paths
GMAIL_SEND_SCRIPT = (
    VAULT / ".claude" / "skills" / "gmail-send" / "scripts" / "send_email.py"
)
LINKEDIN_POST_SCRIPT = (
    VAULT / ".claude" / "skills" / "linkedin-post" / "scripts" / "post_linkedin.py"
)
FACEBOOK_POST_SCRIPT = (
    VAULT / ".claude" / "skills" / "facebook-post" / "scripts" / "post_facebook.py"
)
INSTAGRAM_POST_SCRIPT = (
    VAULT / ".claude" / "skills" / "instagram-post" / "scripts" / "post_instagram.py"
)
TWITTER_POST_SCRIPT = (
    VAULT / ".claude" / "skills" / "twitter-post" / "scripts" / "post_twitter.py"
)
ACCOUNTING_SCRIPT = (
    VAULT / ".claude" / "skills" / "accounting" / "scripts" / "odoo_accounting.py"
)
CEO_BRIEFING_SCRIPT = (
    VAULT / ".claude" / "skills" / "ceo-briefing" / "scripts" / "generate_briefing.py"
)
BRIEFINGS_DIR = VAULT / "Briefings"

SCAN_INTERVAL = 5  # seconds

# ── Rich Console ─────────────────────────────────────────────────────
console = Console()

# ── Classification keywords ──────────────────────────────────────────
URGENT_KEYWORDS     = {"urgent", "asap", "deadline", "overdue", "critical", "immediately"}
ACTIONABLE_KEYWORDS = {"invoice", "reply", "report", "payment", "schedule", "send", "create"}

# ── Skill Detection Keywords ──────────────────────────────────────────
# Each set uses specific platform names — no overlap — so scoring is unambiguous.
GMAIL_KEYWORDS       = {"email", "send", "reply", "mail", "message", "contact", "notify"}
LINKEDIN_KEYWORDS    = {"linkedin"}
FACEBOOK_KEYWORDS    = {"facebook", "fb"}
INSTAGRAM_KEYWORDS   = {"instagram", "ig", "insta"}
TWITTER_KEYWORDS     = {"twitter", "tweet", "x.com"}
ACCOUNTING_KEYWORDS  = {"invoice", "odoo", "accounting", "receivable", "payable", "billing"}
CEO_BRIEFING_KEYWORDS = {"briefing", "ceo", "weekly report", "business audit", "handover", "monday morning"}

# ── Runtime Stats ────────────────────────────────────────────────────
stats = {
    "started_at": None,
    "tasks_triaged": 0,
    "plans_generated": 0,
    "tasks_escalated": 0,
    "skills_executed": 0,
    "tasks_completed": 0,
    "errors": 0,
    "last_event": "—",
    "recent_actions": [],  # last 10 actions
}

# ── Service Health Tracker (Graceful Degradation) ────────────────────
# Tracks the live status of each external service so the Dashboard
# can surface "Service Offline" alerts without crashing the main loop.
#
# Status values: "Online" | "Offline" | "Auth Failed" | "Timeout" | "Unknown"
service_health: dict[str, dict] = {
    "Odoo":      {"status": "Unknown", "last_error": "", "last_check": "—"},
    "Gmail":     {"status": "Unknown", "last_error": "", "last_check": "—"},
    "LinkedIn":  {"status": "Unknown", "last_error": "", "last_check": "—"},
    "Facebook":  {"status": "Unknown", "last_error": "", "last_check": "—"},
    "Instagram": {"status": "Unknown", "last_error": "", "last_check": "—"},
    "Twitter":   {"status": "Unknown", "last_error": "", "last_check": "—"},
}

# Map skill names → service health keys
_SKILL_TO_SERVICE: dict[str, str] = {
    "accounting":     "Odoo",
    "gmail-send":     "Gmail",
    "linkedin-post":  "LinkedIn",
    "facebook-post":  "Facebook",
    "instagram-post": "Instagram",
    "twitter-post":   "Twitter",
    "ceo-briefing":   "Odoo",
}

# (Skill detection keywords defined above near line 63)


# ── YAML Frontmatter Parsing ────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown text.

    Returns (frontmatter_dict, body) where body is everything after
    the closing '---'.
    """
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
        value = line[colon_idx + 1:].strip()
        fm[key] = value
    return fm, body


def build_frontmatter(fm: dict) -> str:
    """Serialize a dict back into YAML frontmatter block."""
    lines = ["---"]
    for key, value in fm.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def rewrite_task_file(path: Path, fm: dict, body: str) -> None:
    """Write updated frontmatter + body back to the task file."""
    content = build_frontmatter(fm) + "\n" + body
    path.write_text(content, encoding="utf-8")


# ── Logging ──────────────────────────────────────────────────────────

def log_action(action_type: str, target: str, result: str, **extra) -> None:
    """Append a JSON audit entry to today's log file."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": "orchestrator",
        "action_type": action_type,
        "target": target,
        "result": result,
    }
    entry.update(extra)
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Service Health: Error Classifier & Updater ───────────────────────

def classify_skill_error(error_msg: str) -> str:
    """Map a raw error string to a human-readable service status.

    Returns one of: "Timeout" | "Auth Failed" | "Offline" | "Error"
    """
    lower = error_msg.lower()
    if "timed out" in lower or "timeout" in lower:
        return "Timeout"
    if any(kw in lower for kw in ("auth", "authentication", "403", "401",
                                   "credentials", "password", "login")):
        return "Auth Failed"
    if any(kw in lower for kw in ("connection refused", "connect", "network",
                                   "unreachable", "max retries", "newconnection")):
        return "Offline"
    return "Error"


def update_service_health(skill: str, success: bool, error_msg: str = "") -> None:
    """Update the service_health dict after a skill execution attempt.

    On failure, classifies the error and logs a structured entry so the
    Dashboard can show a 'Service Offline' alert without crashing the loop.
    """
    service = _SKILL_TO_SERVICE.get(skill)
    if service is None:
        return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    if success:
        service_health[service]["status"]     = "Online"
        service_health[service]["last_error"] = ""
        service_health[service]["last_check"] = ts
        return

    # Failure path
    error_status = classify_skill_error(error_msg)
    service_health[service]["status"]     = error_status
    service_health[service]["last_error"] = error_msg[:120]
    service_health[service]["last_check"] = ts

    log_action(
        "service_health_alert", service, "degraded",
        skill=skill,
        error_status=error_status,
        error_detail=error_msg[:200],
    )
    stats["last_event"] = (
        f"[bold red]⚠ {service} — {error_status}: {error_msg[:60]}[/]"
    )
    console.log(
        f"[bold red]⚠ SERVICE OFFLINE: {service} ({error_status})[/] "
        f"— {error_msg[:80]}"
    )


# ── Classifier ───────────────────────────────────────────────────────

def classify_task(text: str) -> tuple[str, str]:
    """Classify task content into (category, priority).

    Returns one of: ('urgent', 'high'), ('actionable', 'medium'),
    ('informational', 'low').  First match wins (top-down).
    Uses only the body (not frontmatter) and whole-word matching to
    avoid false positives like 'created' matching 'create'.
    """
    _, body = parse_frontmatter(text)
    lower = body.lower()
    for kw in URGENT_KEYWORDS:
        if re.search(rf"\b{kw}\b", lower):
            return "urgent", "high"
    for kw in ACTIONABLE_KEYWORDS:
        if re.search(rf"\b{kw}\b", lower):
            return "actionable", "medium"
    return "informational", "low"


# ── Approval-Boundary Keywords (from Company_Handbook.md) ────────────
# Actions that require human approval before execution
APPROVAL_KEYWORDS = {
    "email", "send", "reply", "contact", "message", "notify",
    "payment", "invoice", "transfer", "charge", "pay", "bill",
    "post", "publish", "tweet", "social media",
}
# Auto-approvable actions (safe, internal, reversible)
SAFE_KEYWORDS = {"read", "summary", "summarize", "log", "analyze", "review", "list"}

# ── Keyword → plan-step mappings ─────────────────────────────────────
ACTION_STEPS = {
    "invoice":  ["Prepare financial document with correct amounts and line items",
                 "Verify amounts and recipients against existing records"],
    "payment":  ["Verify payment amount and recipient details",
                 "Prepare payment authorization document"],
    "reply":    ["Draft response with professional tone",
                 "Review tone and content for accuracy"],
    "send":     ["Draft message/document to send",
                 "Review content and verify recipient"],
    "report":   ["Gather relevant data from available sources",
                 "Compile report with key findings"],
    "schedule": ["Check calendar availability",
                 "Create schedule entry with all details"],
    "create":   ["Define requirements and acceptance criteria",
                 "Create the deliverable"],
}


# ── Risk Assessor ────────────────────────────────────────────────────

def assess_risk(category: str, body_lower: str) -> tuple[str, str]:
    """Determine risk level and explanation.

    Returns (risk_level, factors_explanation).
    """
    has_approval_action = any(
        re.search(rf"\b{kw}\b", body_lower) for kw in APPROVAL_KEYWORDS
    )

    if category == "urgent" or (category == "actionable" and has_approval_action):
        factors = []
        if category == "urgent":
            factors.append("Urgent priority requires immediate attention")
        matched = [kw for kw in APPROVAL_KEYWORDS if re.search(rf"\b{kw}\b", body_lower)]
        if matched:
            factors.append(f"Involves approval-boundary actions: {', '.join(matched[:3])}")
        return "high", ". ".join(factors) or "Urgent task with potential external impact"

    if category == "actionable":
        return "medium", "Actionable task with no direct approval-boundary triggers"

    return "low", "Informational or read-only task with no external impact"


def check_safety(category: str, risk_level: str, body_lower: str) -> tuple[bool, str]:
    """Determine if human approval is needed.

    Returns (needs_approval: bool, reason: str).
    """
    has_approval_action = any(
        re.search(rf"\b{kw}\b", body_lower) for kw in APPROVAL_KEYWORDS
    )

    if risk_level == "high":
        if has_approval_action:
            matched = [kw for kw in APPROVAL_KEYWORDS if re.search(rf"\b{kw}\b", body_lower)]
            return True, (
                f"Task involves actions requiring human approval per Company Handbook: "
                f"{', '.join(matched[:3])}"
            )
        return True, "High-risk or urgent task — human verification recommended before execution"

    if has_approval_action:
        return True, "Contains approval-boundary keywords — human sign-off required"

    return False, "Task involves only internal, reversible, or read-only actions"


# ── Plan Step Builder ────────────────────────────────────────────────

def build_plan_steps(category: str, body_lower: str, needs_approval: bool) -> list[str]:
    """Generate a numbered step list based on task content."""
    steps = []

    # Urgent prefix
    if category == "urgent":
        steps.append("PRIORITY: Assess situation immediately and determine scope of impact")

    # Always start with reading
    steps.append("Read and analyze the source material")

    # Add keyword-specific steps
    added = set()
    for keyword, action_steps in ACTION_STEPS.items():
        if re.search(rf"\b{keyword}\b", body_lower) and keyword not in added:
            steps.extend(action_steps)
            added.add(keyword)

    # If no specific steps matched, add generic ones based on category
    if not added:
        if category == "urgent":
            steps.append("Identify root cause and determine corrective action")
            steps.append("Document findings and recommended resolution")
        elif category == "actionable":
            steps.append("Determine required deliverable and acceptance criteria")
            steps.append("Execute the requested action")
        else:
            steps.append("Summarize key information for reference")

    # Approval gate
    if needs_approval:
        steps.append("Submit for human approval before proceeding")

    # Always log
    steps.append("Log completion to Logs/")

    return steps


# ── Plan File Generator ──────────────────────────────────────────────

def generate_plan(task_path: Path, category: str, priority: str,
                  objective: str, body: str) -> Path | None:
    """Create a Plan_<timestamp>.md file for the given task.

    Returns the Path to the plan file, or None on error.
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    stamp = now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond // 1000:03d}"
    plan_name = f"Plan_{stamp}.md"
    plan_path = NEEDS_ACTION / plan_name

    body_lower = body.lower()

    # Extract original task summary (first meaningful line)
    task_summary = ""
    for line in body.split("\n"):
        stripped = line.strip().lstrip("#").strip()
        if stripped and stripped != "---" and stripped not in (
            "Task Summary", "Full Content", "Objective"
        ):
            task_summary = stripped[:120]
            break
    if not task_summary:
        task_summary = "Review incoming task"

    # Assess risk & safety
    risk_level, risk_factors = assess_risk(category, body_lower)
    needs_approval, safety_reason = check_safety(category, risk_level, body_lower)

    # Build steps
    steps = build_plan_steps(category, body_lower, needs_approval)
    steps_md = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))

    approval_str = "Yes" if needs_approval else "No"

    plan_content = (
        f"---\n"
        f"type: plan\n"
        f"source_task: {task_path.name}\n"
        f"created: {now_iso}\n"
        f"status: pending_review\n"
        f"risk_level: {risk_level}\n"
        f"needs_approval: {'yes' if needs_approval else 'no'}\n"
        f"---\n\n"
        f"## Original Task\n\n"
        f"{task_summary}\n\n"
        f"## Objective\n\n"
        f"{objective}\n\n"
        f"## Step-by-Step Plan\n\n"
        f"{steps_md}\n\n"
        f"## Safety Check\n\n"
        f"**Needs Human Approval:** {approval_str}\n"
        f"**Reason:** {safety_reason}\n\n"
        f"## Risk Level\n\n"
        f"**Level:** {risk_level.capitalize()}\n"
        f"**Factors:** {risk_factors}\n\n"
        f"## FINAL APPROVAL GATE\n\n"
    )

    # Append checkbox — pre-ticked for auto-approved, unticked for needs-approval
    if needs_approval:
        plan_content += (
            "- [ ] **Approve Action:** Tick this box to authorize the "
            "AI Employee to execute this task.\n"
        )
    else:
        plan_content += (
            "- [x] **Approve Action:** Auto-approved — low-risk, "
            "internal-only task.\n"
        )

    try:
        plan_path.write_text(plan_content, encoding="utf-8")
    except Exception as exc:
        stats["errors"] += 1
        log_action("plan_write_error", plan_name, str(exc))
        return None

    # Log plan creation
    log_action(
        "plan_generated", plan_name, "success",
        source_task=task_path.name,
        risk_level=risk_level,
        needs_approval="yes" if needs_approval else "no",
    )

    stats["recent_actions"].append({
        "action": f"Plan {plan_name}",
        "detail": f"for {task_path.name} (risk: {risk_level})",
        "time": now.strftime("%H:%M:%S"),
    })
    stats["recent_actions"] = stats["recent_actions"][-10:]

    return plan_path


# ── Checkbox Approval Scanner ────────────────────────────────────────

def scan_checkbox_approvals() -> int:
    """Scan Needs_Approval/ for Plan files with ticked checkboxes.

    Returns count of plans executed via checkbox approval.
    """
    executed = 0

    for plan_path in sorted(NEEDS_APPROVAL.glob("Plan_*.md")):
        try:
            text = plan_path.read_text(encoding="utf-8")
        except Exception:
            continue

        fm, body = parse_frontmatter(text)

        # Already executed — skip
        if fm.get("status") == "executed":
            continue

        # Quarantine check: FINAL APPROVAL GATE section must exist
        if "## FINAL APPROVAL GATE" not in text:
            fm["status"] = "quarantined"
            fm["quarantined_at"] = datetime.now(timezone.utc).isoformat()
            rewrite_task_file(plan_path, fm, body)
            dest = DONE / plan_path.name
            try:
                shutil.move(str(plan_path), str(dest))
            except Exception:
                pass
            stats["errors"] += 1
            log_action("quarantine", plan_path.name, "missing_approval_gate",
                       reason="FINAL APPROVAL GATE section missing")
            console.log(
                f"[bold red]⚠ Quarantined {plan_path.name} — "
                f"missing FINAL APPROVAL GATE[/]"
            )
            continue

        # Check if checkbox is ticked
        if re.search(r"- \[x\] \*\*Approve Action:\*\*", text):
            now_iso = datetime.now(timezone.utc).isoformat()

            # Find associated task file
            source_task_name = fm.get("source_task", "")
            if source_task_name and not source_task_name.endswith(".md"):
                source_task_name += ".md"
            source_task_path = NEEDS_APPROVAL / source_task_name if source_task_name else None

            # Read task content for skill detection
            task_text = ""
            if source_task_path and source_task_path.exists():
                try:
                    task_text = source_task_path.read_text(encoding="utf-8")
                except Exception:
                    pass

            # Detect and execute skill
            detect_content = task_text or text
            skill = detect_skill(detect_content)
            task_id = fm.get("source_task", plan_path.stem)

            if skill:
                success, output = run_skill(skill, task_id)

                if success:
                    fm["status"] = "executed"
                    fm["executed_at"] = now_iso
                    fm["executed_by"] = skill

                    stats["skills_executed"] += 1
                    stats["last_event"] = (
                        f"[green]✓ Checkbox-approved & executed {skill} "
                        f"for {plan_path.name}[/]"
                    )
                    log_action("checkbox_executed", plan_path.name, "success",
                               skill=skill, task_id=task_id,
                               output=output[:200])
                else:
                    fm["status"] = "skill_failed"
                    fm["error"] = output[:200]

                    stats["errors"] += 1
                    stats["last_event"] = (
                        f"[red]✗ Skill {skill} failed for {plan_path.name}[/]"
                    )
                    log_action("checkbox_executed", plan_path.name, "failed",
                               skill=skill, task_id=task_id,
                               error=output[:200])
            else:
                # No skill needed — mark as done
                fm["status"] = "executed"
                fm["executed_at"] = now_iso
                fm["executed_by"] = "none"
                log_action("checkbox_approved", plan_path.name, "success",
                           note="No skill required — marked done")

            # Write back updated plan
            rewrite_task_file(plan_path, fm, body)

            # Move plan to Done/
            try:
                shutil.move(str(plan_path), str(DONE / plan_path.name))
            except Exception as exc:
                stats["errors"] += 1
                log_action("move_error", plan_path.name, str(exc))

            # Move associated task to Done/
            if source_task_path and source_task_path.exists():
                try:
                    task_fm, task_body = parse_frontmatter(task_text)
                    task_fm["status"] = "executed"
                    task_fm["executed_at"] = now_iso
                    rewrite_task_file(source_task_path, task_fm, task_body)
                    shutil.move(str(source_task_path),
                                str(DONE / source_task_path.name))
                except Exception:
                    pass

            stats["tasks_completed"] += 1
            stats["recent_actions"].append({
                "action": f"Checkbox approved {plan_path.name}",
                "detail": f"skill: {skill or 'none'} → Done/",
                "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            })
            stats["recent_actions"] = stats["recent_actions"][-10:]

            # ── Audit: explicit task_done event closes the chain ──────
            # Chain: task_created → plan_generated → triage →
            #        escalated_to_approval → skill_invoked → [action] →
            #        checkbox_executed → task_done  ← this entry
            log_action(
                "task_done",
                source_task_name or plan_path.name,
                "success",
                plan_file=plan_path.name,
                skill=skill or "none",
                moved_to="Done/",
            )

            executed += 1

        # Unticked checkbox — silently skip (debug-level, no spam)

    return executed


# ── HITL Escalation ──────────────────────────────────────────────────

def escalate_to_approval(task_path: Path, plan_path: Path | None,
                         fm: dict, body: str) -> None:
    """Move a task (and its plan) to Needs_Approval/ for human review.

    Updates the task status to 'awaiting_approval' before moving.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    fm["status"] = "awaiting_approval"
    fm["escalated"] = now_iso

    # Write updated task back before moving
    rewrite_task_file(task_path, fm, body)

    # Move task to Needs_Approval/
    dest_task = NEEDS_APPROVAL / task_path.name
    try:
        shutil.move(str(task_path), str(dest_task))
    except Exception as exc:
        stats["errors"] += 1
        log_action("move_error", task_path.name, str(exc))
        return

    # Move plan alongside if it exists
    if plan_path and plan_path.exists():
        dest_plan = NEEDS_APPROVAL / plan_path.name
        try:
            shutil.move(str(plan_path), str(dest_plan))
        except Exception as exc:
            stats["errors"] += 1
            log_action("move_error", plan_path.name, str(exc))

    stats["tasks_escalated"] += 1
    stats["last_event"] = (
        f"[yellow]⚠ Escalated {task_path.name} → Needs_Approval/[/]"
    )
    stats["recent_actions"].append({
        "action": f"Escalated {task_path.name}",
        "detail": "→ AWAITING HUMAN APPROVAL",
        "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
    })
    stats["recent_actions"] = stats["recent_actions"][-10:]

    log_action("escalated_to_approval", task_path.name, "success",
               plan_file=plan_path.name if plan_path else None)


# ── Skill Detection ──────────────────────────────────────────────────

def detect_skill(text: str) -> str | None:
    """Determine which skill an approved task requires.

    Returns 'gmail-send', 'linkedin-post', 'facebook-post',
    'instagram-post', 'twitter-post', or None.

    Priority:
      1. Frontmatter ``action`` field (explicit binding)
      2. Frontmatter ``skill`` field (direct skill name)
      3. Keyword scoring on the task body
    """
    fm, body = parse_frontmatter(text)

    # 0. If action/skill not in top-level FM, search embedded FM in body
    #    (watcher wraps Inbox files so their frontmatter ends up in ## Full Content)
    if not fm.get("action") and not fm.get("skill"):
        # 0a. Search inside --- ... --- blocks
        for m in re.finditer(r"---\s*\n(.*?)\n---", body, re.DOTALL):
            embedded: dict[str, str] = {}
            for line in m.group(1).split("\n"):
                line = line.strip()
                if not line or ":" not in line:
                    continue
                k, _, v = line.partition(":")
                embedded[k.strip()] = v.strip()
            if embedded.get("action") or embedded.get("skill"):
                fm.update({k: v for k, v in embedded.items() if k not in fm})
                break

        # 0b. Scan bare key:value lines anywhere in body
        #     (Inbox files put skill:/action: after frontmatter, not inside a --- block)
        if not fm.get("action") and not fm.get("skill"):
            for line in body.split("\n"):
                line = line.strip()
                if line.startswith("skill:"):
                    fm["skill"] = line.split(":", 1)[1].strip()
                elif line.startswith("action:"):
                    fm["action"] = line.split(":", 1)[1].strip()
                if fm.get("skill") and fm.get("action"):
                    break

    # 1. Explicit action field
    skill_map = {
        "send_email":           "gmail-send",
        "gmail_send":           "gmail-send",
        "linkedin_post":        "linkedin-post",
        "facebook_post":        "facebook-post",
        "instagram_post":       "instagram-post",
        "twitter_post":         "twitter-post",
        "draft_invoice":        "accounting",
        "post_invoice":         "accounting",
        "fetch_payment_status": "accounting",
        "generate_briefing":    "ceo-briefing",
        "ceo_briefing":         "ceo-briefing",
    }
    action = fm.get("action", "").lower().replace("-", "_")
    if action in skill_map:
        return skill_map[action]

    # 2. Direct skill field
    valid_skills = {
        "gmail-send", "linkedin-post", "facebook-post",
        "instagram-post", "twitter-post", "accounting", "ceo-briefing",
    }
    skill_field = fm.get("skill", "").lower()
    if skill_field in valid_skills:
        return skill_field

    # 3. Keyword scoring on body
    body_lower = body.lower()
    scores: dict[str, int] = {
        "gmail-send":     sum(1 for kw in GMAIL_KEYWORDS         if re.search(rf"\b{re.escape(kw)}\b", body_lower)),
        "linkedin-post":  sum(1 for kw in LINKEDIN_KEYWORDS      if re.search(rf"\b{re.escape(kw)}\b", body_lower)),
        "facebook-post":  sum(1 for kw in FACEBOOK_KEYWORDS      if re.search(rf"\b{re.escape(kw)}\b", body_lower)),
        "instagram-post": sum(1 for kw in INSTAGRAM_KEYWORDS     if re.search(rf"\b{re.escape(kw)}\b", body_lower)),
        "twitter-post":   sum(1 for kw in TWITTER_KEYWORDS       if re.search(rf"\b{re.escape(kw)}\b", body_lower)),
        "accounting":     sum(1 for kw in ACCOUNTING_KEYWORDS    if re.search(rf"\b{re.escape(kw)}\b", body_lower)),
        "ceo-briefing":   sum(1 for kw in CEO_BRIEFING_KEYWORDS  if re.search(rf"\b{re.escape(kw)}\b", body_lower)),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def run_skill(skill_name: str, task_id: str) -> tuple[bool, str]:
    """Execute a skill script as a subprocess.

    Timeouts:
      • Browser-based skills: 180 s (login + page interactions)
      • Accounting / CEO Briefing: 60 s (JSON-RPC only, no browser)
      • Gmail send: 120 s

    On any failure the service health tracker is updated so the Dashboard
    can surface a 'Service Offline' alert without crashing the loop.

    Returns (success, output_or_error).
    """
    scripts: dict[str, Path] = {
        "gmail-send":     GMAIL_SEND_SCRIPT,
        "linkedin-post":  LINKEDIN_POST_SCRIPT,
        "facebook-post":  FACEBOOK_POST_SCRIPT,
        "instagram-post": INSTAGRAM_POST_SCRIPT,
        "twitter-post":   TWITTER_POST_SCRIPT,
        "accounting":     ACCOUNTING_SCRIPT,      # Fix: was missing
        "ceo-briefing":   CEO_BRIEFING_SCRIPT,    # Gold Tier addition
    }
    script = scripts.get(skill_name)
    if not script:
        return False, f"Unknown skill: {skill_name}"

    if not script.exists():
        error = f"Skill script not found: {script}"
        update_service_health(skill_name, False, error)
        return False, error

    BROWSER_SKILLS = {"linkedin-post", "facebook-post", "instagram-post", "twitter-post"}
    API_SKILLS     = {"accounting", "ceo-briefing"}
    if skill_name in BROWSER_SKILLS:
        timeout = 180
    elif skill_name in API_SKILLS:
        timeout = 60
    else:
        timeout = 120

    import os as _os
    env = _os.environ.copy()
    # Forward display env so headless=false works in WSL2 (WSLg)
    if skill_name in BROWSER_SKILLS:
        env.setdefault("DISPLAY", ":0")
        env.setdefault("WAYLAND_DISPLAY", "wayland-0")
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{_os.getuid()}")

    try:
        result = subprocess.run(
            [sys.executable, str(script), "--task-id", task_id],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(VAULT), env=env,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            error = result.stderr.strip() or output or "Non-zero exit"
            update_service_health(skill_name, False, error)
            return False, error

        update_service_health(skill_name, True)
        return True, output

    except subprocess.TimeoutExpired:
        error = f"Skill execution timed out ({timeout}s)"
        update_service_health(skill_name, False, error)
        return False, error
    except Exception as exc:
        update_service_health(skill_name, False, str(exc))
        return False, str(exc)


# ── Approved Task Processor ──────────────────────────────────────────

def process_approved() -> int:
    """Scan Approved/ for human-approved files, execute skills, finalize.

    Returns count of tasks processed.
    """
    processed = 0
    for path in sorted(APPROVED.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        fm, body = parse_frontmatter(text)
        status = fm.get("status", "").lower()

        # Only process files the human has marked as 'approved'
        if status != "approved":
            continue

        # Determine which skill to run
        skill = detect_skill(text)
        task_id = fm.get("source_task", path.stem)
        now_iso = datetime.now(timezone.utc).isoformat()

        if skill:
            # Execute the skill
            success, output = run_skill(skill, task_id)

            if success:
                fm["status"] = "executed"
                fm["executed_at"] = now_iso
                fm["executed_by"] = skill

                stats["skills_executed"] += 1
                stats["last_event"] = (
                    f"[green]✓ Executed {skill} for {path.name}[/]"
                )
                stats["recent_actions"].append({
                    "action": f"Skill: {skill}",
                    "detail": f"for {path.name} → OK",
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                })
                stats["recent_actions"] = stats["recent_actions"][-10:]

                log_action("skill_executed", path.name, "success",
                           skill=skill, task_id=task_id, output=output[:200])
            else:
                fm["status"] = "skill_failed"
                fm["error"] = output[:200]

                stats["errors"] += 1
                stats["last_event"] = (
                    f"[red]✗ Skill {skill} failed for {path.name}[/]"
                )
                stats["recent_actions"].append({
                    "action": f"Skill: {skill}",
                    "detail": f"for {path.name} → FAILED",
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                })
                stats["recent_actions"] = stats["recent_actions"][-10:]

                log_action("skill_executed", path.name, "failed",
                           skill=skill, task_id=task_id, error=output[:200])
        else:
            # No skill needed — just mark as done
            fm["status"] = "done"
            fm["completed_at"] = now_iso
            log_action("approved_completed", path.name, "success",
                       note="No skill required")

        # Write back updated file
        updated = build_frontmatter(fm) + "\n" + body
        path.write_text(updated, encoding="utf-8")

        # Move to Done/
        dest = DONE / path.name
        try:
            shutil.move(str(path), str(dest))
            stats["tasks_completed"] += 1
            log_action("task_completed", path.name, "success",
                       final_status=fm["status"])
        except Exception as exc:
            stats["errors"] += 1
            log_action("move_error", path.name, str(exc))

        # Also move the source TASK file from Needs_Approval/ to Done/
        # if it's still there
        source_task_name = fm.get("source_task", "")
        if source_task_name:
            # Ensure .md extension
            if not source_task_name.endswith(".md"):
                source_task_name += ".md"
            source_in_approval = NEEDS_APPROVAL / source_task_name
            if source_in_approval.exists():
                try:
                    shutil.move(str(source_in_approval),
                                str(DONE / source_task_name))
                except Exception:
                    pass
            # Also move associated plan
            plan_name = fm.get("plan_file", "")
            if plan_name:
                if not plan_name.endswith(".md"):
                    plan_name += ".md"
                plan_in_approval = NEEDS_APPROVAL / plan_name
                if plan_in_approval.exists():
                    try:
                        shutil.move(str(plan_in_approval),
                                    str(DONE / plan_name))
                    except Exception:
                        pass

        processed += 1

    return processed


# ── Objective Generator ──────────────────────────────────────────────

def generate_objective(category: str, body: str) -> str:
    """Generate a one-line objective from the task body."""
    # Find the first meaningful line (non-empty, non-heading-marker-only)
    for line in body.split("\n"):
        stripped = line.strip().lstrip("#").strip()
        # Skip empty lines, section dividers, and section headers we added
        if not stripped or stripped == "---" or stripped in (
            "Task Summary", "Full Content", "Objective"
        ):
            continue
        # Use this as the basis for the objective
        summary = stripped[:120]
        if category == "urgent":
            return f"URGENT: {summary}"
        return summary
    return "Review and process this task."


# ── Triage Pipeline ──────────────────────────────────────────────────

def triage_task(path: Path) -> bool:
    """Triage a single pending task file. Returns True if triaged."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        stats["errors"] += 1
        log_action("read_error", path.name, str(exc))
        return False

    fm, body = parse_frontmatter(text)

    # Only process pending_triage tasks
    if fm.get("status") != "pending_triage":
        return False

    # Classify
    category, priority = classify_task(text)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Generate objective
    objective = generate_objective(category, body)

    # ── Silver Tier: Generate reasoning plan ─────────────────────────
    plan_path = generate_plan(path, category, priority, objective, body)
    plan_ref = plan_path.name if plan_path else None
    if plan_path:
        stats["plans_generated"] += 1

    # Check if this task needs human approval
    body_lower = body.lower()
    risk_level, _ = assess_risk(category, body_lower)
    needs_approval, safety_reason = check_safety(category, risk_level, body_lower)

    # Update frontmatter
    fm["status"] = category
    fm["priority"] = priority
    fm["triaged"] = now_iso
    if plan_ref:
        fm["plan_file"] = plan_ref

    # For actionable/urgent tasks, insert ## Objective after # Task Summary
    if category in ("actionable", "urgent"):
        lines = body.split("\n")
        new_lines = []
        inserted = False
        for line in lines:
            new_lines.append(line)
            if not inserted and line.strip().startswith("# Task Summary"):
                new_lines.append("")
                new_lines.append("## Objective")
                new_lines.append("")
                new_lines.append(objective)
                inserted = True
        if not inserted:
            new_lines = ["", "## Objective", "", objective, ""] + lines
        body = "\n".join(new_lines)

    # ── HITL Gate: Escalate if approval needed ────────────────────────
    if needs_approval:
        fm["needs_approval"] = "yes"
        fm["approval_reason"] = safety_reason
        escalate_to_approval(path, plan_path, fm, body)

        stats["tasks_triaged"] += 1
        log_action("triage", path.name, "escalated", category=category,
                   priority=priority, plan_file=plan_ref,
                   approval_reason=safety_reason)
        return True

    # ── No HITL required — still route through Needs_Approval/ ──────
    # The plan is pre-ticked [x]. Moving it there lets scan_checkbox_approvals()
    # find and execute the skill on the next 5-second scan cycle, preserving
    # the full audit chain without requiring human interaction.
    fm["needs_approval"] = "no"
    fm["auto_approved"]  = "yes"
    escalate_to_approval(path, plan_path, fm, body)

    stats["tasks_triaged"] += 1
    plan_note = f" + {plan_ref}" if plan_ref else ""
    stats["last_event"] = (
        f"[cyan]✓ Triaged {path.name} → auto-approved {category}{plan_note}[/]"
    )
    stats["recent_actions"].append({
        "action": f"Triaged {path.name}",
        "detail": f"→ auto-approved {category}{plan_note}",
        "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
    })
    stats["recent_actions"] = stats["recent_actions"][-10:]

    log_action("triage", path.name, "auto_approved", category=category,
               priority=priority, plan_file=plan_ref)
    return True


# ── Completion Handler ───────────────────────────────────────────────

def check_completions() -> int:
    """Move tasks with status approved/done to Done/. Returns count moved."""
    moved = 0
    for path in NEEDS_ACTION.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        fm, _ = parse_frontmatter(text)
        status = fm.get("status", "").lower()

        if status in ("approved", "done"):
            dest = DONE / path.name
            try:
                shutil.move(str(path), str(dest))
                moved += 1
                stats["tasks_completed"] += 1
                stats["last_event"] = f"[blue]→ Moved {path.name} to Done/[/]"
                stats["recent_actions"].append({
                    "action": f"Completed {path.name}",
                    "detail": f"→ Done/ (status: {status})",
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                })
                stats["recent_actions"] = stats["recent_actions"][-10:]
                log_action("task_completed", path.name, "success", new_status=status)
            except Exception as exc:
                stats["errors"] += 1
                log_action("move_error", path.name, str(exc))

    return moved


# ── Dashboard Updater ────────────────────────────────────────────────

def update_dashboard(triaged_files: list[tuple[str, str]] | None = None) -> None:
    """Rewrite Dashboard.md with current state.

    triaged_files: list of (filename, category) just triaged this cycle.
    """
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Collect all active tasks from Needs_Action/ (skip Plan_ files)
    active_tasks = []
    for path in sorted(NEEDS_ACTION.glob("*.md")):
        if path.name.startswith("Plan_"):
            continue  # Plans are metadata, not standalone tasks
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        fm, body = parse_frontmatter(text)
        # Extract first heading or first 60 chars for task name
        task_name = ""
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                task_name = stripped.lstrip("#").strip()[:60]
                break
        if not task_name:
            task_name = body.strip()[:60] or path.stem

        # Show linked plan if present
        plan_ref = fm.get("plan_file", "")
        status_display = fm.get("status", "—")
        if plan_ref:
            status_display += " (planned)"

        active_tasks.append({
            "file": path.name,
            "task": task_name,
            "source": fm.get("source", "—"),
            "priority": fm.get("priority", "—"),
            "status": status_display,
            "created": fm.get("created", "—"),
        })

    # Build active tasks table rows
    task_rows = ""
    for i, t in enumerate(active_tasks, 1):
        task_rows += (
            f"| {i}   | {t['task'][:44]:<44} | {t['source']:<6} "
            f"| {t['priority']:<8} | {t['status']:<11} | {t['created'][:20]:<20} |\n"
        )
    if not task_rows:
        task_rows = "| —   | _No active tasks._                           | —      | —        | —           | —                    |\n"

    # Build recent activity entries for newly triaged files
    new_activity_rows = ""
    if triaged_files:
        for filename, category in triaged_files:
            new_activity_rows += (
                f"| {now_iso:<20} | Triaged {filename} → {category.capitalize():<30} | Success |\n"
            )

    # Read existing dashboard to preserve recent activity history
    existing_activity = ""
    if DASHBOARD.exists():
        try:
            dash_text = DASHBOARD.read_text(encoding="utf-8")
            # Extract existing activity rows (skip header rows)
            in_activity = False
            for line in dash_text.split("\n"):
                if "## Recent Activity" in line:
                    in_activity = True
                    continue
                if in_activity and line.startswith("| ") and not line.startswith("| Timestamp") and not line.startswith("| ---"):
                    existing_activity += line + "\n"
                elif in_activity and line.startswith("##"):
                    break
        except Exception:
            pass

    # Collect items awaiting human approval from Needs_Approval/
    pending_items = []
    for path in sorted(NEEDS_APPROVAL.glob("*.md")):
        if path.name.startswith("Plan_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        fm, body = parse_frontmatter(text)
        task_name = ""
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                task_name = stripped.lstrip("#").strip()[:50]
                break
        if not task_name:
            task_name = body.strip()[:50] or path.stem
        reason = fm.get("approval_reason", "Requires human approval")[:50]
        pending_items.append({
            "file": path.name,
            "task": task_name,
            "priority": fm.get("priority", "—"),
            "reason": reason,
            "escalated": fm.get("escalated", fm.get("created", "—"))[:20],
        })

    # Check checkbox status in associated plan files
    for item in pending_items:
        # Look for the plan file linked to this task
        task_file = NEEDS_APPROVAL / item["file"]
        checkbox_status = "—"
        try:
            task_text = task_file.read_text(encoding="utf-8")
            task_fm, _ = parse_frontmatter(task_text)
            plan_name = task_fm.get("plan_file", "")
            if plan_name:
                if not plan_name.endswith(".md"):
                    plan_name += ".md"
                plan_file = NEEDS_APPROVAL / plan_name
                if plan_file.exists():
                    plan_text = plan_file.read_text(encoding="utf-8")
                    if re.search(r"- \[x\] \*\*Approve Action:\*\*", plan_text):
                        checkbox_status = "Approved"
                    elif re.search(r"- \[ \] \*\*Approve Action:\*\*", plan_text):
                        checkbox_status = "Checkbox Pending"
        except Exception:
            pass
        item["checkbox"] = checkbox_status

    if pending_items:
        pending_approvals_section = (
            "| # | Task | Priority | Status | Reason | Escalated |\n"
            "| --- | ---- | -------- | ------ | ------ | --------- |\n"
        )
        for i, p in enumerate(pending_items, 1):
            pending_approvals_section += (
                f"| {i} | {p['task']:<50} | {p['priority']:<8} "
                f"| {p['checkbox']:<16} "
                f"| {p['reason']:<50} | {p['escalated']:<20} |\n"
            )
        pending_approvals_section += (
            "\n> **Action Required:** Review items above. "
            "Tick the checkbox in the Plan file to approve."
        )
    else:
        pending_approvals_section = "_No items pending approval._"

    # ── Service Health Rows ───────────────────────────────────────────
    def _health_icon(status: str) -> str:
        icons = {
            "Online":      "🟢 Online",
            "Offline":     "🔴 Offline",
            "Auth Failed": "🔴 Auth Failed",
            "Timeout":     "🟡 Timeout",
            "Error":       "🟡 Error",
            "Unknown":     "⚪ Unknown",
        }
        return icons.get(status, f"⚪ {status}")

    service_rows = ""
    for svc, info in service_health.items():
        icon  = _health_icon(info["status"])
        err   = info["last_error"][:50] if info["last_error"] else "—"
        check = info["last_check"][:20]
        service_rows += (
            f"| {svc:<12} | {icon:<20} | {check:<20} | {err} |\n"
        )

    # ── Alerts for offline services ───────────────────────────────────
    offline_services = [
        svc for svc, info in service_health.items()
        if info["status"] in ("Offline", "Auth Failed", "Timeout", "Error")
    ]
    if offline_services:
        alert_block = (
            "\n> **⚠ Service Alert:** The following services are degraded: "
            + ", ".join(f"**{s}**" for s in offline_services)
            + ". Check `.env` credentials and network connectivity.\n"
        )
    else:
        alert_block = ""

    dashboard_content = f"""---
title: AI Employee Dashboard
last_updated: {now_iso}
version: 0.2.1
---

# AI Employee Dashboard

## System Status

| Component     | Status  | Last Check           |
| ------------- | ------- | -------------------- |
| Orchestrator  | Online  | {now_iso:<20} |
| Gmail Watcher | Offline | —                    |
| File Watcher  | Online  | {now_iso:<20} |
| Claude Code   | Online  | {now_iso:<20} |

## Service Health
{alert_block}
| Service      | Status               | Last Check           | Last Error                                        |
| ------------ | -------------------- | -------------------- | ------------------------------------------------- |
{service_rows}

## Active Tasks

| ID  | Task                                         | Source | Priority | Status      | Created              |
| --- | -------------------------------------------- | ------ | -------- | ----------- | -------------------- |
{task_rows}
## Pending Approvals

{pending_approvals_section}

## Recent Activity

| Timestamp            | Action                                                     | Result  |
| -------------------- | ---------------------------------------------------------- | ------- |
{new_activity_rows}{existing_activity}
## Recent Logs

_See `/Logs/` for full audit trail._

---

## E2E Validation Summary (Gold Tier — 2026-03-02)

| Skill         | Result             | Notes                                                      |
| ------------- | ------------------ | ---------------------------------------------------------- |
| CEO Briefing  | ✅ Success          | `Briefings/Briefing_2026-03-02.md` generated               |
| LinkedIn Post | ✅ Live Post        | **Confirmed on feed** — `Logs/linkedin_post_*.png`         |
| Twitter/X     | ⚠️ Auth Challenge  | Browser launched; 2FA required — init session manually     |
| Facebook      | ⚠️ Session Needed  | Browser launched; no saved cookies — init session manually |
| Odoo Invoice  | ⚠️ Bug Fixed       | Embedded FM bug fixed; re-run once Odoo is reachable       |

## Bug Fixes Applied (v0.2.1)

| Bug | Root Cause | Fix |
| --- | ---------- | --- |
| Odoo `unknown_action` | `action:` field in embedded body FM, not top-level YAML | Embedded FM fallback in `odoo_accounting.py` |
| Social skills leak YAML | `---..---` block included in post content | Strip leading FM block in all 4 social skill extractors |

---
*Generated by AI Employee v0.2.1 — Gold Tier*
"""
    try:
        DASHBOARD.write_text(dashboard_content, encoding="utf-8")
    except Exception as exc:
        stats["errors"] += 1
        log_action("dashboard_error", "Dashboard.md", str(exc))


# ── Rich TUI ─────────────────────────────────────────────────────────

def build_status_table() -> Table:
    """Build a live-updating status table."""
    table = Table(
        title="Orchestrator Status",
        title_style="bold green",
        border_style="bright_green",
        show_lines=True,
        expand=True,
    )
    table.add_column("Metric", style="bold white", min_width=18)
    table.add_column("Value", style="green")

    uptime = "—"
    if stats["started_at"]:
        delta = datetime.now(timezone.utc) - stats["started_at"]
        mins, secs = divmod(int(delta.total_seconds()), 60)
        hrs, mins = divmod(mins, 60)
        uptime = f"{hrs:02d}h {mins:02d}m {secs:02d}s"

    needs_count = len(list(NEEDS_ACTION.glob("*.md")))
    approval_count = len(list(NEEDS_APPROVAL.glob("*.md")))
    approved_count = len(list(APPROVED.glob("*.md")))
    done_count = len(list(DONE.glob("*.md")))

    table.add_row("Status", "[bold green]● ONLINE[/]")
    table.add_row("Uptime", uptime)
    table.add_row("Scan Interval", f"{SCAN_INTERVAL}s")
    table.add_row("Needs Action", f"[yellow]{needs_count}[/]")
    table.add_row("Needs Approval", f"[bold yellow]{approval_count}[/]" if approval_count else "0")
    table.add_row("Approved Queue", f"[bold cyan]{approved_count}[/]" if approved_count else "0")
    table.add_row("Done", f"[blue]{done_count}[/]")
    table.add_row("Triaged", f"[cyan]{stats['tasks_triaged']}[/]")
    table.add_row("Plans", f"[magenta]{stats['plans_generated']}[/]")
    table.add_row("Escalated", f"[yellow]{stats['tasks_escalated']}[/]")
    table.add_row("Skills Run", f"[green]{stats['skills_executed']}[/]")
    table.add_row("Completed", f"[blue]{stats['tasks_completed']}[/]")
    table.add_row("Errors", f"[red]{stats['errors']}[/]" if stats["errors"] else "0")
    table.add_row("Last Event", stats["last_event"])

    # ── Service health rows ───────────────────────────────────────────
    table.add_section()
    table.add_row("[bold]Service", "[bold]Status", end_section=False)
    status_style = {
        "Online":      "green",
        "Offline":     "bold red",
        "Auth Failed": "bold red",
        "Timeout":     "yellow",
        "Error":       "yellow",
        "Unknown":     "dim",
    }
    for svc, info in service_health.items():
        st    = info["status"]
        style = status_style.get(st, "dim")
        table.add_row(svc, f"[{style}]{st}[/]")

    return table


def build_recent_table() -> Table:
    """Build table of recent orchestrator actions."""
    table = Table(
        title="Recent Actions",
        title_style="bold magenta",
        border_style="bright_magenta",
        expand=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Action", style="bold white")
    table.add_column("Detail", style="cyan")
    table.add_column("Time", style="green")

    if not stats["recent_actions"]:
        table.add_row("—", "[dim]Waiting for tasks…[/]", "—", "—")
    else:
        for i, action in enumerate(reversed(stats["recent_actions"]), 1):
            table.add_row(str(i), action["action"], action["detail"], action["time"])

    return table


def build_dashboard_layout() -> Layout:
    """Compose the full Rich dashboard layout."""
    layout = Layout()
    layout.split_column(
        Layout(
            Panel(
                Text.from_markup(
                    "[bold green]  AI EMPLOYEE — ORCHESTRATOR[/]\n"
                    "[dim]Decision Layer • Local-First • Autonomous[/]"
                ),
                border_style="bright_green",
                padding=(1, 2),
            ),
            name="header",
            size=5,
        ),
        Layout(name="body"),
        Layout(
            Panel(
                Text.from_markup(
                    "[dim]Press [bold]Ctrl+C[/bold] to stop  •  "
                    f"Scanning every {SCAN_INTERVAL}s  •  "
                    "Logs → Logs/<date>.json[/]"
                ),
                border_style="dim",
            ),
            name="footer",
            size=3,
        ),
    )
    layout["body"].split_row(
        Layout(Panel(build_status_table(), border_style="bright_green"), name="status"),
        Layout(Panel(build_recent_table(), border_style="bright_magenta"), name="recent"),
    )
    return layout


# ── Main Loop ────────────────────────────────────────────────────────

def main() -> None:
    for d in (NEEDS_ACTION, NEEDS_APPROVAL, APPROVED, DONE, LOGS, BRIEFINGS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    stats["started_at"] = datetime.now(timezone.utc)

    # ── Banner ────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel.fit(
            "[bold green]AI EMPLOYEE — ORCHESTRATOR[/]\n"
            "[dim]Decision Layer v0.2 (Gold Tier)  •  Local-First  •  Autonomous[/]\n\n"
            f"[white]Scanning:  [/] [yellow]{NEEDS_ACTION}[/]\n"
            f"[white]Approval:  [/] [yellow]{NEEDS_APPROVAL}[/]\n"
            f"[white]Approved:  [/] [yellow]{APPROVED}[/]\n"
            f"[white]Done:      [/] [yellow]{DONE}[/]\n"
            f"[white]Briefings: [/] [yellow]{BRIEFINGS_DIR}[/]\n"
            f"[white]Dashboard: [/] [yellow]{DASHBOARD}[/]\n"
            f"[white]Logs:      [/] [yellow]{LOGS}[/]",
            border_style="bright_green",
            padding=(1, 2),
        )
    )
    console.print()

    log_action("orchestrator_start", "orchestrator", "success")

    # ── Graceful shutdown ─────────────────────────────────────────────
    shutdown_requested = False

    def _shutdown(sig, _frame):
        nonlocal shutdown_requested
        shutdown_requested = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── Live Dashboard + Scan Loop ────────────────────────────────────
    try:
        with Live(build_dashboard_layout(), console=console, refresh_per_second=1) as live:
            while not shutdown_requested:
                # 1. Triage pending tasks
                triaged_this_cycle = []
                for path in sorted(NEEDS_ACTION.glob("*.md")):
                    name = path.name  # capture before potential move
                    if triage_task(path):
                        # File may have been moved to Needs_Approval/
                        if path.exists():
                            fm, _ = parse_frontmatter(
                                path.read_text(encoding="utf-8")
                            )
                            triaged_this_cycle.append(
                                (name, fm.get("status", "unknown"))
                            )
                        else:
                            triaged_this_cycle.append(
                                (name, "awaiting_approval")
                            )

                # 1.5 Scan checkbox approvals in Needs_Approval/
                scan_checkbox_approvals()

                # 2. Process approved tasks (legacy HITL gate)
                process_approved()

                # 3. Check for completed tasks in Needs_Action/
                check_completions()

                # 4. Update Dashboard.md
                update_dashboard(
                    triaged_this_cycle if triaged_this_cycle else None
                )

                # 5. Refresh TUI
                live.update(build_dashboard_layout())

                # 6. Wait for next scan
                for _ in range(SCAN_INTERVAL):
                    if shutdown_requested:
                        break
                    time.sleep(1)
                    live.update(build_dashboard_layout())

    except KeyboardInterrupt:
        pass

    # ── Goodbye ───────────────────────────────────────────────────────
    log_action("orchestrator_stop", "orchestrator", "graceful")

    console.print()
    console.print(
        Panel.fit(
            f"[bold yellow]Orchestrator stopped.[/]\n"
            f"[dim]Triaged [cyan]{stats['tasks_triaged']}[/] tasks  •  "
            f"Plans [magenta]{stats['plans_generated']}[/]  •  "
            f"Escalated [yellow]{stats['tasks_escalated']}[/]  •  "
            f"Skills [green]{stats['skills_executed']}[/]  •  "
            f"Completed [blue]{stats['tasks_completed']}[/]  •  "
            f"[red]{stats['errors']}[/] errors[/]",
            border_style="yellow",
        )
    )


if __name__ == "__main__":
    main()
