"use client";

import { useEffect, useState } from "react";
import {
  Mail, Database, Linkedin, Facebook, Instagram, Twitter,
  Server, Eye, RefreshCw, MessageSquare, FileText,
} from "lucide-react";
import clsx from "clsx";

interface Service {
  id: string;
  label: string;
  status: "online" | "offline" | "stopped" | "configured" | "unknown";
  detail: string;
}

interface HealthData {
  services: Service[];
  counts: { inbox: number; action: number; ralph: number };
  timestamp: string;
}

const ICONS: Record<string, React.ElementType> = {
  orchestrator: Server,
  "gmail-watcher": Mail,
  watcher: FileText,
  "whatsapp-watcher": MessageSquare,
  odoo: Database,
  linkedin: Linkedin,
  facebook: Facebook,
  instagram: Instagram,
  twitter: Twitter,
};

const STATUS_CONFIG = {
  online:     { dot: "bg-heagent-online",  ring: "shadow-[0_0_10px_rgba(16,185,129,0.5)]",  label: "Online",     text: "text-heagent-online" },
  offline:    { dot: "bg-heagent-offline", ring: "shadow-[0_0_10px_rgba(239,68,68,0.5)]",   label: "Offline",    text: "text-heagent-offline" },
  stopped:    { dot: "bg-heagent-warn",    ring: "shadow-[0_0_10px_rgba(245,158,11,0.5)]",  label: "Stopped",    text: "text-heagent-warn" },
  configured: { dot: "bg-heagent-info",    ring: "",                                          label: "Configured", text: "text-heagent-info" },
  unknown:    { dot: "bg-slate-600",       ring: "",                                          label: "Unknown",    text: "text-slate-500" },
};

function StatusDot({ status }: { status: Service["status"] }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.unknown;
  return (
    <span className="relative flex h-3 w-3 shrink-0">
      {(status === "online") && (
        <span className={clsx("animate-ping absolute inline-flex h-full w-full rounded-full opacity-60", cfg.dot)} />
      )}
      <span className={clsx("relative inline-flex rounded-full h-3 w-3", cfg.dot, cfg.ring)} />
    </span>
  );
}

export function ServiceHealth() {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      const res = await fetch("/api/health", { cache: "no-store" });
      if (res.ok) {
        setData(await res.json());
        setLastUpdated(new Date());
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30_000);
    return () => clearInterval(interval);
  }, []);

  const onlineCount = data?.services.filter(
    (s) => s.status === "online" || s.status === "configured"
  ).length ?? 0;
  const total = data?.services.length ?? 0;

  return (
    <div className="card space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-white">Service Health</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {data ? `${onlineCount}/${total} services active` : "Loading…"}
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          aria-label="Refresh health status"
          className="btn-ghost px-2 py-2 text-slate-400 hover:text-heagent-cyan"
        >
          <RefreshCw className={clsx("w-4 h-4", loading && "animate-spin")} aria-hidden />
        </button>
      </div>

      {/* Service Grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {(data?.services ?? Array.from({ length: 9 }, (_, i) => ({
          id: String(i), label: "—", status: "unknown" as const, detail: "…",
        }))).map((svc) => {
          const Icon = ICONS[svc.id] ?? Server;
          const cfg  = STATUS_CONFIG[svc.status] ?? STATUS_CONFIG.unknown;
          return (
            <div
              key={svc.id}
              className="flex flex-col gap-2 rounded-lg border border-heagent-border bg-heagent-deep p-3
                         transition-colors duration-200 hover:border-heagent-cyan/30"
            >
              <div className="flex items-center justify-between">
                <Icon className="w-4 h-4 text-slate-400" aria-hidden />
                <StatusDot status={svc.status} />
              </div>
              <div>
                <p className="text-sm font-medium text-white leading-tight">{svc.label}</p>
                <p className={clsx("text-xs mt-0.5 font-mono", cfg.text)}>{svc.detail}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary counters */}
      {data && (
        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-heagent-border">
          {[
            { label: "Inbox",       value: data.counts.inbox,  color: "text-heagent-info" },
            { label: "Needs Action",value: data.counts.action, color: "text-heagent-warn" },
            { label: "Ralph Loop",  value: `${data.counts.ralph}/5`, color: "text-heagent-purple" },
          ].map((item) => (
            <div key={item.label} className="text-center">
              <p className={clsx("text-xl font-bold font-mono", item.color)}>{item.value}</p>
              <p className="text-xs text-slate-500">{item.label}</p>
            </div>
          ))}
        </div>
      )}

      {lastUpdated && (
        <p className="text-xs text-slate-600 text-right">
          Updated {lastUpdated.toLocaleTimeString()}
        </p>
      )}
    </div>
  );
}
