"""
Ralph Wiggum — Claude Code Stop Hook (Gold Tier)
=================================================
Implements the "Ralph Wiggum" persistence loop: intercepts Claude's
exit and re-injects the processing prompt when there is still work
pending in Needs_Action/ or Needs_Approval/.

How it works (Claude Code Stop hook contract):
  Exit 0          → Claude stops normally (work is done or max iterations hit)
  Exit non-zero   → Claude re-injects this script's stdout as a new user
                    message and continues the agentic loop

State is tracked in Logs/ralph_state.json:
  { "iteration": N, "session_id": "<ISO timestamp>", "last_pending": [...] }

Configuration (via environment or defaults):
  RALPH_MAX_ITERATIONS=5   Maximum re-injection cycles before forced stop
  RALPH_VAULT_PATH         Path to vault root (default: script's directory)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────
VAULT             = Path(os.getenv("RALPH_VAULT_PATH", Path(__file__).resolve().parent))
NEEDS_ACTION      = VAULT / "Needs_Action"
NEEDS_APPROVAL    = VAULT / "Needs_Approval"
DONE              = VAULT / "Done"
LOGS              = VAULT / "Logs"
STATE_FILE        = LOGS / "ralph_state.json"
MAX_ITERATIONS    = int(os.getenv("RALPH_MAX_ITERATIONS", "5"))

# ── Helpers ───────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"iteration": 0, "session_id": _now_iso(), "last_pending": []}


def _save_state(state: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _log_ralph(event: str, detail: str, iteration: int) -> None:
    """Append a structured log entry to today's audit log."""
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp":   _now_iso(),
        "actor":       "ralph-wiggum",
        "action_type": event,
        "target":      "stop-hook",
        "result":      detail,
        "iteration":   iteration,
    }
    log_file = LOGS / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _pending_tasks() -> list[str]:
    """
    Return names of task files (not Plan_ files) that are still pending.

    A task is "pending" if it exists in Needs_Action/ or Needs_Approval/
    with a status that is NOT 'executed', 'done', 'approved', or 'completed'.
    """
    import re

    def _status(path: Path) -> str:
        try:
            text  = path.read_text(encoding="utf-8")
            match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            if not match:
                return "unknown"
            for line in match.group(1).split("\n"):
                line = line.strip()
                if line.startswith("status:"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return "unknown"

    pending = []
    terminal_states = {"executed", "done", "approved", "completed",
                       "awaiting_approval", "skill_failed"}

    for folder in (NEEDS_ACTION, NEEDS_APPROVAL):
        if not folder.exists():
            continue
        for path in folder.glob("*.md"):
            if path.name.startswith("Plan_"):
                continue  # Plans are metadata, not work items
            st = _status(path)
            # awaiting_approval means escalated → human must act → not Claude's job
            if st == "awaiting_approval":
                continue
            if st not in terminal_states:
                pending.append(path.name)

    return pending


# ── Main Logic ────────────────────────────────────────────────────────

def main() -> int:
    """
    Returns exit code:
      0  → allow Claude to stop (done or max iterations)
      2  → re-inject prompt (work remains, iteration < max)
    """
    LOGS.mkdir(parents=True, exist_ok=True)

    state     = _load_state()
    iteration = state.get("iteration", 0)
    pending   = _pending_tasks()

    # ── Nothing left to do → let Claude stop ─────────────────────────
    if not pending:
        _log_ralph("loop_exit", "no_pending_tasks", iteration)
        _save_state({"iteration": 0, "session_id": _now_iso(), "last_pending": []})
        return 0

    # ── Max iterations reached → force stop with warning ─────────────
    if iteration >= MAX_ITERATIONS:
        _log_ralph("loop_exit", f"max_iterations_reached ({MAX_ITERATIONS})", iteration)
        _save_state({"iteration": 0, "session_id": state["session_id"], "last_pending": []})
        print(
            f"[Ralph Wiggum] Max iterations ({MAX_ITERATIONS}) reached.\n"
            f"Stopping to prevent infinite loop.\n"
            f"Pending tasks that need manual review: {', '.join(pending)}\n"
            f"Check Needs_Action/ and Needs_Approval/ in your vault."
        )
        # Exit 0 — let Claude stop but surface the warning
        return 0

    # ── Work remains → re-inject the processing prompt ───────────────
    iteration += 1
    state["iteration"]    = iteration
    state["last_pending"] = pending
    _save_state(state)

    _log_ralph("loop_continue", f"iteration_{iteration}_of_{MAX_ITERATIONS}", iteration)

    # The text printed to stdout becomes Claude's new user message
    pending_list = "\n".join(f"  - {p}" for p in pending)
    print(
        f"[Ralph Wiggum Loop — Iteration {iteration}/{MAX_ITERATIONS}]\n\n"
        f"There are still pending tasks in the vault that have not been moved to Done/:\n"
        f"{pending_list}\n\n"
        f"INSTRUCTIONS:\n"
        f"1. Check /Needs_Action/ for any tasks with status 'pending_triage' and triage them.\n"
        f"2. Check /Needs_Approval/ for any Plan files with an unticked checkbox — DO NOT "
        f"auto-approve; wait for human tick.\n"
        f"3. If a task has been approved (checkbox ticked) but its skill has not run, run it now.\n"
        f"4. After processing, move the completed task files to /Done/.\n"
        f"5. When all tasks are in /Done/, your work is complete — stop normally.\n\n"
        f"Proceed and complete the pending work."
    )
    return 2  # Non-zero → Claude re-injects stdout and continues


if __name__ == "__main__":
    sys.exit(main())
