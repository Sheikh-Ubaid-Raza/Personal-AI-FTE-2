"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText, ChevronRight, Calendar, CheckCircle, WifiOff, RefreshCw } from "lucide-react";
import clsx from "clsx";

interface BriefingSummary {
  filename:       string;
  date:           string;
  tasksCompleted: number;
  odooOnline:     boolean;
}

interface BriefingFull extends BriefingSummary {
  content: string;
}

export function BriefingViewer() {
  const [briefings, setBriefings]   = useState<BriefingSummary[]>([]);
  const [selected, setSelected]     = useState<BriefingFull | null>(null);
  const [loading, setLoading]       = useState(true);
  const [loadingFull, setLoadingFull] = useState(false);

  async function loadList() {
    setLoading(true);
    try {
      const res  = await fetch("/api/briefings", { cache: "no-store" });
      const data = await res.json() as { briefings: BriefingSummary[] };
      setBriefings(data.briefings);
      // Auto-select the latest
      if (data.briefings.length > 0 && !selected) {
        await loadBriefing(data.briefings[0].filename);
      }
    } finally {
      setLoading(false);
    }
  }

  async function loadBriefing(filename: string) {
    setLoadingFull(true);
    try {
      const res  = await fetch(`/api/briefings?file=${encodeURIComponent(filename)}`, { cache: "no-store" });
      const data = await res.json() as BriefingFull;
      setSelected(data);
    } finally {
      setLoadingFull(false);
    }
  }

  useEffect(() => { loadList(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const dateLabel = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric" });
    } catch { return dateStr; }
  };

  // Strip YAML frontmatter from content before rendering
  const cleanContent = (content: string) =>
    content.replace(/^---[\s\S]*?---\s*\n?/, "").trim();

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:gap-6 min-h-0">
      {/* Sidebar — briefing list */}
      <div className="lg:w-64 shrink-0 space-y-2">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-white">CEO Briefings</h2>
          <button onClick={loadList} disabled={loading} aria-label="Refresh briefings" className="btn-ghost px-2 py-1.5">
            <RefreshCw className={clsx("w-3.5 h-3.5 text-slate-400", loading && "animate-spin")} aria-hidden />
          </button>
        </div>

        {loading && (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-lg bg-heagent-deep animate-pulse" />)}
          </div>
        )}

        {!loading && briefings.length === 0 && (
          <div className="card text-center py-8">
            <FileText className="w-8 h-8 text-slate-600 mx-auto mb-2" aria-hidden />
            <p className="text-xs text-slate-500">No briefings yet</p>
          </div>
        )}

        {briefings.map((b) => (
          <button
            key={b.filename}
            onClick={() => loadBriefing(b.filename)}
            aria-pressed={selected?.filename === b.filename}
            className={clsx(
              "w-full rounded-lg border p-3 text-left transition-all duration-200 space-y-1",
              "hover:border-heagent-cyan/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-heagent-cyan",
              selected?.filename === b.filename
                ? "border-heagent-cyan bg-heagent-cyan/10"
                : "border-heagent-border bg-heagent-deep"
            )}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-white truncate flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-heagent-cyan shrink-0" aria-hidden />
                {dateLabel(b.date)}
              </span>
              <ChevronRight className="w-3.5 h-3.5 text-slate-600 shrink-0" aria-hidden />
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <CheckCircle className="w-3 h-3 text-heagent-online" aria-hidden />
              {b.tasksCompleted} tasks
              {b.odooOnline
                ? <span className="text-heagent-online">· Odoo</span>
                : <span className="flex items-center gap-0.5 text-slate-600"><WifiOff className="w-3 h-3" aria-hidden /> offline</span>
              }
            </div>
          </button>
        ))}
      </div>

      {/* Main — markdown content */}
      <div className="flex-1 min-w-0">
        {loadingFull && (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className={clsx("rounded-lg bg-heagent-deep animate-pulse", i === 1 ? "h-8 w-2/3" : "h-4")} />
            ))}
          </div>
        )}

        {!loadingFull && selected && (
          <div className="prose-heagent max-h-[70vh] overflow-y-auto pr-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {cleanContent(selected.content)}
            </ReactMarkdown>
          </div>
        )}

        {!loadingFull && !selected && !loading && (
          <div className="card flex flex-col items-center py-16">
            <FileText className="w-12 h-12 text-slate-600 mb-3" aria-hidden />
            <p className="text-sm text-slate-500">Select a briefing to read</p>
          </div>
        )}
      </div>
    </div>
  );
}
