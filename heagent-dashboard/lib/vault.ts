/**
 * lib/vault.ts
 * Server-side helpers for reading the Obsidian vault filesystem.
 * All functions are async and safe — they never throw, always return defaults.
 */

import fs from "fs/promises";
import path from "path";

export const VAULT = process.env.VAULT_PATH ?? "/mnt/c/h-0/AI_Employee_Vault_bronze";

// ── Frontmatter parser ────────────────────────────────────────────────
export function parseFrontmatter(text: string): { fm: Record<string, string>; body: string } {
  const match = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)/);
  if (!match) return { fm: {}, body: text };
  const fm: Record<string, string> = {};
  for (const line of match[1].split("\n")) {
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    fm[line.slice(0, idx).trim()] = line.slice(idx + 1).trim().replace(/^["']|["']$/g, "");
  }
  return { fm, body: match[2] };
}

// ── Approvals ─────────────────────────────────────────────────────────
export interface ApprovalFile {
  filename: string;
  sourcetask: string;
  riskLevel: string;
  needsApproval: string;
  status: string;
  approved: boolean;
  body: string;
  created: string;
}

export async function listApprovals(): Promise<ApprovalFile[]> {
  const dir = path.join(VAULT, "Needs_Approval");
  try {
    const files = await fs.readdir(dir);
    const mdFiles = files.filter((f) => f.endsWith(".md")).sort().reverse();
    const results: ApprovalFile[] = [];
    for (const filename of mdFiles) {
      try {
        const text = await fs.readFile(path.join(dir, filename), "utf-8");
        const { fm, body } = parseFrontmatter(text);
        results.push({
          filename,
          sourcetask:    fm.source_task    ?? "",
          riskLevel:     fm.risk_level     ?? "medium",
          needsApproval: fm.needs_approval ?? "yes",
          status:        fm.status         ?? "pending_review",
          approved:      text.includes("- [x] **Approve Action:**"),
          body,
          created:       fm.created        ?? "",
        });
      } catch {
        // skip unreadable files
      }
    }
    return results;
  } catch {
    return [];
  }
}

export async function approveTask(filename: string): Promise<{ ok: boolean; message: string }> {
  const dir  = path.join(VAULT, "Needs_Approval");
  const file = path.join(dir, filename);
  // Security: disallow path traversal
  if (!file.startsWith(dir)) return { ok: false, message: "Invalid filename" };
  try {
    const text    = await fs.readFile(file, "utf-8");
    const updated = text.replace(
      "- [ ] **Approve Action:**",
      "- [x] **Approve Action:**"
    );
    if (updated === text) return { ok: false, message: "Checkbox not found or already approved" };
    await fs.writeFile(file, updated, "utf-8");
    return { ok: true, message: "Approved" };
  } catch (err) {
    return { ok: false, message: String(err) };
  }
}

// ── Activity Log ──────────────────────────────────────────────────────
export interface LogEntry {
  timestamp:   string;
  actor:       string;
  action_type: string;
  target:      string;
  result:      string;
  [key: string]: unknown;
}

export async function getRecentActivity(limit = 20): Promise<LogEntry[]> {
  const logsDir = path.join(VAULT, "Logs");
  try {
    const files = await fs.readdir(logsDir);
    const jsonFiles = files
      .filter((f) => f.match(/^\d{4}-\d{2}-\d{2}\.json$/))
      .sort()
      .reverse()
      .slice(0, 3); // last 3 days

    const entries: LogEntry[] = [];
    for (const file of jsonFiles) {
      try {
        const text  = await fs.readFile(path.join(logsDir, file), "utf-8");
        const lines = text.trim().split("\n").filter(Boolean);
        for (const line of lines) {
          try { entries.push(JSON.parse(line)); } catch { /* skip */ }
        }
      } catch { /* skip */ }
    }
    return entries.sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, limit);
  } catch {
    return [];
  }
}

// ── Briefings ─────────────────────────────────────────────────────────
export interface Briefing {
  filename: string;
  date: string;
  content: string;
  tasksCompleted: number;
  odooOnline: boolean;
}

export async function listBriefings(): Promise<Briefing[]> {
  const dir = path.join(VAULT, "Briefings");
  try {
    const files = await fs.readdir(dir);
    const mdFiles = files.filter((f) => f.endsWith(".md")).sort().reverse();
    const results: Briefing[] = [];
    for (const filename of mdFiles) {
      try {
        const content = await fs.readFile(path.join(dir, filename), "utf-8");
        const { fm }  = parseFrontmatter(content);
        results.push({
          filename,
          date:           fm.generated ?? filename.replace("Briefing_", "").replace(".md", ""),
          content,
          tasksCompleted: parseInt(fm.tasks_completed ?? "0", 10),
          odooOnline:     fm.odoo_online === "true",
        });
      } catch { /* skip */ }
    }
    return results;
  } catch {
    return [];
  }
}

// ── Ralph Wiggum State ────────────────────────────────────────────────
export interface RalphState {
  iteration:   number;
  session_id:  string;
  last_pending: string[];
}

export async function getRalphState(): Promise<RalphState> {
  const file = path.join(VAULT, "Logs", "ralph_state.json");
  try {
    const text = await fs.readFile(file, "utf-8");
    return JSON.parse(text);
  } catch {
    return { iteration: 0, session_id: "", last_pending: [] };
  }
}

// ── Inbox count ───────────────────────────────────────────────────────
export async function getInboxCount(): Promise<number> {
  try {
    const files = await fs.readdir(path.join(VAULT, "Inbox"));
    return files.filter((f) => f.endsWith(".md")).length;
  } catch {
    return 0;
  }
}

export async function getNeedsActionCount(): Promise<number> {
  try {
    const files = await fs.readdir(path.join(VAULT, "Needs_Action"));
    return files.filter((f) => f.endsWith(".md")).length;
  } catch {
    return 0;
  }
}

export async function getDoneCount(): Promise<number> {
  try {
    const files = await fs.readdir(path.join(VAULT, "Done"));
    return files.filter((f) => f.endsWith(".md")).length;
  } catch {
    return 0;
  }
}
