"use client";

import { useEffect, useState, useCallback } from "react";
import { CheckSquare, FileText, ChevronDown, ChevronUp, AlertTriangle, Clock, RefreshCw, Shield } from "lucide-react";
import clsx from "clsx";

interface ApprovalFile {
  filename:      string;
  sourcetask:    string;
  riskLevel:     string;
  needsApproval: string;
  status:        string;
  approved:      boolean;
  body:          string;
  created:       string;
}

const RISK_CONFIG: Record<string, { bg: string; text: string; icon: React.ElementType }> = {
  high:   { bg: "bg-heagent-offline/10 border-heagent-offline/30", text: "text-heagent-offline", icon: AlertTriangle },
  medium: { bg: "bg-heagent-warn/10   border-heagent-warn/30",    text: "text-heagent-warn",    icon: Clock },
  low:    { bg: "bg-heagent-info/10   border-heagent-info/30",    text: "text-heagent-info",    icon: Shield },
};

function ApprovalCard({ item, onApprove }: { item: ApprovalFile; onApprove: () => void }) {
  const [expanded, setExpanded]   = useState(false);
  const [approving, setApproving] = useState(false);
  const [approved, setApproved]   = useState(item.approved);
  const [toast, setToast]         = useState("");

  const risk    = RISK_CONFIG[item.riskLevel] ?? RISK_CONFIG.medium;
  const RiskIcon = risk.icon;

  async function handleApprove() {
    setApproving(true);
    try {
      const res = await fetch("/api/approve", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ filename: item.filename }),
      });
      const data = await res.json() as { ok: boolean; message: string };
      if (data.ok) {
        setApproved(true);
        setToast("Approved! Orchestrator will execute on next cycle.");
        onApprove();
      } else {
        setToast(`Error: ${data.message}`);
      }
    } catch {
      setToast("Network error — try again.");
    } finally {
      setApproving(false);
      setTimeout(() => setToast(""), 4000);
    }
  }

  const dateStr = item.created
    ? new Date(item.created).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })
    : "—";

  // Body preview: strip frontmatter, take first 200 chars
  const preview = item.body.replace(/^---[\s\S]*?---\s*/m, "").trim().slice(0, 200);

  return (
    <div className={clsx(
      "rounded-xl border p-4 transition-all duration-200 space-y-3",
      approved ? "border-heagent-online/30 bg-heagent-online/5 opacity-60"
               : clsx("border-heagent-border bg-heagent-deep hover:border-heagent-cyan/30")
    )}>
      {/* Title row */}
      <div className="flex items-start gap-3">
        <RiskIcon className={clsx("w-4 h-4 mt-0.5 shrink-0", risk.text)} aria-hidden />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">{item.filename}</p>
          <p className="text-xs text-slate-500 mt-0.5">
            Source: <span className="text-slate-400 font-mono">{item.sourcetask || "—"}</span>
            &nbsp;· {dateStr}
          </p>
        </div>
        <span className={clsx(
          "badge shrink-0",
          item.riskLevel === "high" ? "badge-offline" :
          item.riskLevel === "medium" ? "badge-warn" : "badge-info"
        )}>
          {item.riskLevel} risk
        </span>
      </div>

      {/* Preview / expand */}
      <div className="text-xs text-slate-400 font-mono leading-relaxed bg-heagent-void rounded-lg p-3
                      border border-heagent-border overflow-hidden">
        {expanded ? item.body : (preview + (preview.length < 200 ? "" : "…"))}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          aria-label="Toggle plan details"
          className="btn-ghost px-3 py-1.5 text-xs"
        >
          <FileText className="w-3.5 h-3.5" aria-hidden />
          {expanded ? "Collapse" : "View Plan"}
          {expanded
            ? <ChevronUp  className="w-3.5 h-3.5" aria-hidden />
            : <ChevronDown className="w-3.5 h-3.5" aria-hidden />}
        </button>

        {!approved && (
          <button
            onClick={handleApprove}
            disabled={approving}
            aria-label={`Approve task ${item.filename}`}
            className="btn-primary px-3 py-1.5 text-xs ml-auto"
          >
            <CheckSquare className="w-3.5 h-3.5" aria-hidden />
            {approving ? "Approving…" : "Approve"}
          </button>
        )}

        {approved && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-heagent-online font-medium">
            <CheckSquare className="w-3.5 h-3.5" aria-hidden />
            Approved
          </span>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <p className={clsx(
          "text-xs rounded-lg px-3 py-2 toast-enter",
          toast.startsWith("Error") || toast.startsWith("Network")
            ? "bg-heagent-offline/20 text-heagent-offline"
            : "bg-heagent-online/20 text-heagent-online"
        )}>
          {toast}
        </p>
      )}
    </div>
  );
}

export function ApprovalCenter() {
  const [items, setItems]     = useState<ApprovalFile[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res  = await fetch("/api/approvals", { cache: "no-store" });
      const data = await res.json() as { approvals: ApprovalFile[] };
      setItems(data.approvals);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 20_000);
    return () => clearInterval(interval);
  }, [load]);

  const pending  = items.filter((i) => !i.approved);
  const done     = items.filter((i) =>  i.approved);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-white">HITL Approval Center</h2>
          <p className="text-xs text-slate-500">
            {pending.length} pending &nbsp;·&nbsp; {done.length} approved
          </p>
        </div>
        <button onClick={load} disabled={loading} aria-label="Refresh approvals" className="btn-ghost px-2 py-2">
          <RefreshCw className={clsx("w-4 h-4 text-slate-400", loading && "animate-spin")} aria-hidden />
        </button>
      </div>

      {loading && items.length === 0 && (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="rounded-xl border border-heagent-border bg-heagent-deep p-4 animate-pulse h-28" />
          ))}
        </div>
      )}

      {!loading && items.length === 0 && (
        <div className="card text-center py-12">
          <CheckSquare className="w-10 h-10 text-heagent-online mx-auto mb-3" aria-hidden />
          <p className="text-sm font-medium text-white">All clear!</p>
          <p className="text-xs text-slate-500 mt-1">No tasks awaiting approval.</p>
        </div>
      )}

      {pending.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-medium text-heagent-warn uppercase tracking-wider">
            Awaiting Approval ({pending.length})
          </p>
          {pending.map((item) => (
            <ApprovalCard key={item.filename} item={item} onApprove={load} />
          ))}
        </div>
      )}

      {done.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-medium text-heagent-online uppercase tracking-wider mt-4">
            Approved ({done.length})
          </p>
          {done.map((item) => (
            <ApprovalCard key={item.filename} item={item} onApprove={load} />
          ))}
        </div>
      )}
    </div>
  );
}
