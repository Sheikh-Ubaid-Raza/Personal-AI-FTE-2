import { NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";
import { isOdooOnline } from "@/lib/odoo";
import { getInboxCount, getNeedsActionCount, getRalphState } from "@/lib/vault";

const execAsync = promisify(exec);

export const dynamic = "force-dynamic";
export const revalidate = 0;

interface Pm2Process {
  name: string;
  pm2_env: { status: string; pm_uptime?: number };
}

async function getPm2Status(): Promise<Record<string, "online" | "stopped" | "unknown">> {
  try {
    const { stdout } = await execAsync("pm2 jlist", { timeout: 5000 });
    const procs = JSON.parse(stdout) as Pm2Process[];
    const status: Record<string, "online" | "stopped" | "unknown"> = {};
    for (const p of procs) {
      status[p.name] = p.pm2_env?.status === "online" ? "online" : "stopped";
    }
    return status;
  } catch {
    return {};
  }
}

export async function GET() {
  const [pm2, odooOnline, inboxCount, actionCount, ralph] = await Promise.all([
    getPm2Status(),
    isOdooOnline(),
    getInboxCount(),
    getNeedsActionCount(),
    getRalphState(),
  ]);

  // Derive service statuses
  const services = [
    {
      id:      "orchestrator",
      label:   "Orchestrator",
      status:  pm2["orchestrator"] ?? "unknown",
      detail:  pm2["orchestrator"] === "online" ? "Running" : "Stopped",
    },
    {
      id:      "gmail-watcher",
      label:   "Gmail Watcher",
      status:  pm2["gmail-watcher"] ?? "unknown",
      detail:  pm2["gmail-watcher"] === "online" ? "Polling every 2 min" : "Stopped",
    },
    {
      id:      "watcher",
      label:   "File Watcher",
      status:  pm2["watcher"] ?? pm2["file-watcher"] ?? "unknown",
      detail:  "Monitoring Inbox/",
    },
    {
      id:      "whatsapp-watcher",
      label:   "WhatsApp Watcher",
      status:  pm2["whatsapp-watcher"] ?? "unknown",
      detail:  pm2["whatsapp-watcher"] === "online" ? "Polling every 60s" : "Stopped",
    },
    {
      id:      "odoo",
      label:   "Odoo ERP",
      status:  odooOnline ? "online" : "offline",
      detail:  odooOnline ? "JSON-RPC connected" : "Unreachable",
    },
    {
      id:      "linkedin",
      label:   "LinkedIn",
      status:  "configured",
      detail:  "Playwright session ready",
    },
    {
      id:      "facebook",
      label:   "Facebook",
      status:  "configured",
      detail:  "Playwright session ready",
    },
    {
      id:      "instagram",
      label:   "Instagram",
      status:  "configured",
      detail:  "Playwright session ready",
    },
    {
      id:      "twitter",
      label:   "Twitter/X",
      status:  "configured",
      detail:  "Playwright session ready",
    },
  ];

  return NextResponse.json({
    services,
    counts: { inbox: inboxCount, action: actionCount, ralph: ralph.iteration },
    ralph,
    timestamp: new Date().toISOString(),
  });
}
