"use client";

import { useEffect, useState, useRef } from "react";
import { Activity, CheckCircle, XCircle, Clock, RefreshCw, Zap } from "lucide-react";
import clsx from "clsx";
import { formatDistanceToNow } from "date-fns";

interface LogEntry {
  timestamp:   string;
  actor:       string;
  action_type: string;
  target:      string;
  result:      string;
  [key: string]: unknown;
}

const ACTOR_COLORS: Record<string, string> = {
  orchestrator:        "text-heagent-cyan",
  "ceo-briefing":      "text-purple-400",
  "ralph-wiggum":      "text-yellow-400",
  "inbox_watcher":     "text-heagent-info",
  "gmail-send-skill":  "text-red-400",
  "linkedin-post-skill": "text-blue-400",
  "facebook-post-skill": "text-blue-500",
  "instagram-post-skill":"text-pink-400",
  "twitter-post-skill":  "text-sky-400",
  "accounting-skill":    "text-green-400",
  "file-triage-skill":   "text-orange-400",
  "task-planner":        "text-indigo-400",
};

const RESULT_ICON: Record<string, React.ElementType> = {
  success:     CheckCircle,
  "in_progress": Clock,
  started:     Zap,
  failed:      XCircle,
  dry_run:     Clock,
};

const RESULT_COLOR: Record<string, string> = {
  success:     "text-heagent-online",
  "in_progress": "text-heagent-warn",
  started:     "text-heagent-info",
  failed:      "text-heagent-offline",
  dry_run:     "text-slate-500",
};

function LogRow({ entry, isNew }: { entry: LogEntry; isNew: boolean }) {
  const ResultIcon = RESULT_ICON[entry.result] ?? Activity;
  const actorColor = ACTOR_COLORS[entry.actor] ?? "text-slate-400";
  const resultColor = RESULT_COLOR[entry.result] ?? "text-slate-400";

  let timeAgo = "—";
  try { timeAgo = formatDistanceToNow(new Date(entry.timestamp), { addSuffix: true }); } catch { /* skip */ }

  return (
    <div className={clsx(
      "flex items-start gap-3 px-4 py-2.5 border-b border-heagent-border/50 hover:bg-heagent-deep/50 transition-colors duration-150",
      isNew && "animate-slide-in bg-heagent-cyan/5"
    )}>
      <ResultIcon className={clsx("w-3.5 h-3.5 mt-0.5 shrink-0", resultColor)} aria-hidden />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className={clsx("text-xs font-medium font-mono", actorColor)}>
            {entry.actor}
          </span>
          <span className="text-xs text-slate-500 truncate">
            {entry.action_type.replace(/_/g, " ")}
          </span>
        </div>
        <p className="text-xs text-slate-400 truncate mt-0.5">
          {entry.target}
        </p>
      </div>
      <div className="text-right shrink-0">
        <span className={clsx("text-xs font-medium", resultColor)}>
          {entry.result}
        </span>
        <p className="text-xs text-slate-600 mt-0.5 whitespace-nowrap">{timeAgo}</p>
      </div>
    </div>
  );
}

export function ActivityFeed() {
  const [entries, setEntries]   = useState<LogEntry[]>([]);
  const [loading, setLoading]   = useState(true);
  const [newKeys, setNewKeys]   = useState<Set<string>>(new Set());
  const prevKeys                = useRef<Set<string>>(new Set());

  async function load() {
    try {
      const res  = await fetch("/api/activity?limit=20", { cache: "no-store" });
      const data = await res.json() as { activity: LogEntry[] };
      const incoming = data.activity;

      // Detect genuinely new entries
      const fresh = new Set<string>();
      for (const e of incoming) {
        const key = `${e.timestamp}:${e.actor}:${e.action_type}`;
        if (!prevKeys.current.has(key)) fresh.add(key);
      }
      prevKeys.current = new Set(incoming.map((e) => `${e.timestamp}:${e.actor}:${e.action_type}`));

      setEntries(incoming);
      if (fresh.size > 0) {
        setNewKeys(fresh);
        setTimeout(() => setNewKeys(new Set()), 3000);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 15_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="card !p-0 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-heagent-border">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-heagent-cyan" aria-hidden />
          <h2 className="text-sm font-semibold text-white">Live Activity Feed</h2>
          <span className="badge badge-info">{entries.length}</span>
        </div>
        <button onClick={load} disabled={loading} aria-label="Refresh activity" className="btn-ghost px-2 py-1.5">
          <RefreshCw className={clsx("w-3.5 h-3.5 text-slate-400", loading && "animate-spin")} aria-hidden />
        </button>
      </div>

      {/* Column headers */}
      <div className="flex items-center gap-3 px-4 py-2 bg-heagent-deep border-b border-heagent-border/50">
        <div className="w-3.5 shrink-0" />
        <span className="flex-1 text-xs text-slate-600 uppercase tracking-wider">Actor · Action</span>
        <span className="text-xs text-slate-600 uppercase tracking-wider shrink-0">Status</span>
      </div>

      {/* Entries */}
      <div className="max-h-96 overflow-y-auto">
        {loading && entries.length === 0 && (
          <div className="space-y-0">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-12 border-b border-heagent-border/50 animate-pulse px-4 flex items-center gap-3">
                <div className="w-3.5 h-3.5 rounded-full bg-heagent-border" />
                <div className="flex-1 h-3 rounded bg-heagent-border" />
                <div className="w-16 h-3 rounded bg-heagent-border" />
              </div>
            ))}
          </div>
        )}

        {entries.map((entry) => {
          const key = `${entry.timestamp}:${entry.actor}:${entry.action_type}`;
          return <LogRow key={key} entry={entry} isNew={newKeys.has(key)} />;
        })}

        {!loading && entries.length === 0 && (
          <div className="flex flex-col items-center py-12 text-center px-4">
            <Activity className="w-8 h-8 text-slate-600 mb-2" aria-hidden />
            <p className="text-xs text-slate-500">No activity logged yet.</p>
          </div>
        )}
      </div>
    </div>
  );
}
