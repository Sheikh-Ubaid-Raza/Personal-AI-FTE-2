"use client";

import { useEffect, useState } from "react";
import { RefreshCw, Zap, CheckCircle, AlertTriangle } from "lucide-react";
import clsx from "clsx";

interface RalphData {
  iteration:    number;
  session_id:   string;
  last_pending: string[];
  counts:       { inbox: number; action: number; done: number };
  maxIterations: number;
  isLooping:    boolean;
}

export function RalphStatus() {
  const [data, setData]       = useState<RalphData | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const res = await fetch("/api/ralph", { cache: "no-store" });
      if (res.ok) setData(await res.json());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 20_000);
    return () => clearInterval(interval);
  }, []);

  const iter    = data?.iteration      ?? 0;
  const maxIter = data?.maxIterations  ?? 5;
  const pct     = Math.min((iter / maxIter) * 100, 100);

  const statusColor = !data
    ? "text-slate-500"
    : iter === 0
    ? "text-heagent-online"
    : iter >= maxIter
    ? "text-heagent-offline"
    : "text-heagent-warn";

  const statusLabel = !data
    ? "Unknown"
    : iter === 0
    ? "Idle — all tasks complete"
    : iter >= maxIter
    ? "Max iterations reached"
    : `Looping — iteration ${iter}/${maxIter}`;

  return (
    <div className="card space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-heagent-warn" aria-hidden />
          <h2 className="text-sm font-semibold text-white">Ralph Wiggum Loop</h2>
        </div>
        <button onClick={load} disabled={loading} aria-label="Refresh Ralph status" className="btn-ghost px-2 py-1.5">
          <RefreshCw className={clsx("w-3.5 h-3.5 text-slate-400", loading && "animate-spin")} aria-hidden />
        </button>
      </div>

      {/* Status */}
      <div className="flex items-center gap-2">
        {iter === 0
          ? <CheckCircle className="w-4 h-4 text-heagent-online" aria-hidden />
          : <AlertTriangle className="w-4 h-4 text-heagent-warn" aria-hidden />
        }
        <span className={clsx("text-sm font-medium", statusColor)}>{statusLabel}</span>
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex justify-between text-xs text-slate-500 mb-1">
          <span>Iterations used</span>
          <span className="font-mono">{iter} / {maxIter}</span>
        </div>
        <div className="h-2 bg-heagent-deep rounded-full overflow-hidden border border-heagent-border">
          <div
            className={clsx(
              "h-full rounded-full transition-all duration-500",
              iter === 0         ? "bg-heagent-online" :
              iter >= maxIter    ? "bg-heagent-offline" :
                                   "bg-heagent-warn"
            )}
            style={{ width: `${pct}%` }}
            role="progressbar"
            aria-valuenow={iter}
            aria-valuemin={0}
            aria-valuemax={maxIter}
            aria-label="Ralph Wiggum loop iteration progress"
          />
        </div>
      </div>

      {/* Vault counters */}
      {data && (
        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-heagent-border">
          {[
            { label: "Inbox",   value: data.counts.inbox,  color: "text-heagent-info" },
            { label: "Action",  value: data.counts.action, color: "text-heagent-warn" },
            { label: "Done",    value: data.counts.done,   color: "text-heagent-online" },
          ].map((c) => (
            <div key={c.label} className="text-center">
              <p className={clsx("text-lg font-bold font-mono", c.color)}>{c.value}</p>
              <p className="text-xs text-slate-500">{c.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Pending tasks */}
      {data?.last_pending && data.last_pending.length > 0 && (
        <div>
          <p className="text-xs text-slate-500 mb-1.5">Last seen pending:</p>
          <div className="space-y-1">
            {data.last_pending.map((task) => (
              <p key={task} className="text-xs font-mono text-heagent-warn truncate bg-heagent-deep rounded px-2 py-1">
                {task}
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Session ID */}
      {data?.session_id && (
        <p className="text-xs text-slate-600 font-mono truncate">
          Session: {data.session_id.slice(0, 24)}…
        </p>
      )}
    </div>
  );
}
