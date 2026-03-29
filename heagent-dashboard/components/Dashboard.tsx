"use client";

/**
 * Dashboard.tsx — Main Heagent AI Employee Control Panel
 *
 * Sections:
 *  1. Overview      — Service Health grid + Ralph Wiggum loop + counters
 *  2. Approvals     — HITL Approval Center (tick checkbox from UI)
 *  3. Finance       — Odoo financial charts + overdue invoices
 *  4. CEO Briefings — Markdown briefing viewer
 *  5. Activity Feed — Real-time log stream
 *
 * Design: Futuristic Healthcare (Heagent brand)
 * Tech:   Next.js App Router, Tailwind CSS, Recharts, Lucide icons
 */

import { useState } from "react";
import { Sidebar, MobileNav } from "./Sidebar";
import { ServiceHealth }    from "./ServiceHealth";
import { ApprovalCenter }   from "./ApprovalCenter";
import { FinancialInsights } from "./FinancialInsights";
import { BriefingViewer }   from "./BriefingViewer";
import { ActivityFeed }     from "./ActivityFeed";
import { RalphStatus }      from "./RalphStatus";
import {
  LayoutDashboard, CheckSquare, BarChart2, BookOpen, Activity,
} from "lucide-react";

const SECTION_ICONS: Record<string, React.ElementType> = {
  overview:  LayoutDashboard,
  approvals: CheckSquare,
  finance:   BarChart2,
  briefings: BookOpen,
  activity:  Activity,
};

const SECTION_TITLES: Record<string, string> = {
  overview:  "System Overview",
  approvals: "HITL Approval Center",
  finance:   "Executive Financial Insights",
  briefings: "CEO Briefings",
  activity:  "Live Activity Feed",
};

export function Dashboard() {
  const [active, setActive] = useState("overview");

  const Icon  = SECTION_ICONS[active] ?? LayoutDashboard;
  const title = SECTION_TITLES[active] ?? "";

  return (
    <div className="flex h-screen overflow-hidden bg-heagent-void dot-grid">
      {/* Glow overlay */}
      <div className="pointer-events-none fixed inset-0 bg-glow-cyan opacity-60" aria-hidden />
      <div className="pointer-events-none fixed inset-0 bg-glow-purple opacity-40" aria-hidden />

      {/* Desktop sidebar */}
      <div className="hidden lg:flex relative z-10">
        <Sidebar active={active} onChange={setActive} />
      </div>

      {/* Main content */}
      <div className="flex flex-col flex-1 min-w-0 relative z-10 overflow-hidden">
        {/* Topbar */}
        <header className="flex items-center gap-4 px-6 py-4 border-b border-heagent-border bg-heagent-deep/80 backdrop-blur-xl shrink-0">
          {/* Logo (mobile) */}
          <div className="flex items-center gap-2 lg:hidden">
            <div className="w-7 h-7 rounded-md bg-gradient-to-br from-heagent-cyan to-heagent-purple
                            flex items-center justify-center shadow-glow-cyan">
              <span className="text-white font-bold text-xs font-mono">H</span>
            </div>
          </div>

          <Icon className="w-5 h-5 text-heagent-cyan hidden sm:block" aria-hidden />
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-semibold text-white">{title}</h1>
            <p className="text-xs text-slate-500 hidden sm:block">
              Heagent AI Employee · Gold Tier · Local-First Autonomous System
            </p>
          </div>

          {/* Live indicator */}
          <div className="flex items-center gap-2 shrink-0">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-heagent-online opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-heagent-online" />
            </span>
            <span className="text-xs text-heagent-online font-medium hidden sm:block">Live</span>
          </div>
        </header>

        {/* Page content */}
        <main
          id="main-content"
          className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 pb-20 lg:pb-6"
        >
          {active === "overview" && (
            <div className="space-y-5 max-w-7xl mx-auto animate-fade-in">
              {/* Service Health full-width */}
              <ServiceHealth />

              {/* Two-column: Ralph + a quick-action card */}
              <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
                <div className="lg:col-span-1">
                  <RalphStatus />
                </div>
                <div className="lg:col-span-2">
                  <ActivityFeed />
                </div>
              </div>

              {/* Quick links */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  { label: "View Approvals",  tab: "approvals", icon: CheckSquare, color: "text-heagent-warn",   bg: "bg-heagent-warn/10   border-heagent-warn/20" },
                  { label: "Financial Report",tab: "finance",   icon: BarChart2,   color: "text-heagent-cyan",   bg: "bg-heagent-cyan/10   border-heagent-cyan/20" },
                  { label: "CEO Briefing",    tab: "briefings", icon: BookOpen,    color: "text-purple-400",     bg: "bg-purple-900/20     border-purple-700/30" },
                  { label: "Activity Log",    tab: "activity",  icon: Activity,    color: "text-heagent-info",   bg: "bg-heagent-info/10   border-heagent-info/20" },
                ].map(({ label, tab, icon: QIcon, color, bg }) => (
                  <button
                    key={tab}
                    onClick={() => setActive(tab)}
                    aria-label={`Go to ${label}`}
                    className={`rounded-xl border p-4 text-left transition-all duration-200 hover:scale-[1.02]
                                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-heagent-cyan ${bg}`}
                  >
                    <QIcon className={`w-5 h-5 ${color} mb-2`} aria-hidden />
                    <p className="text-xs font-medium text-white">{label}</p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {active === "approvals" && (
            <div className="max-w-3xl mx-auto animate-fade-in">
              <ApprovalCenter />
            </div>
          )}

          {active === "finance" && (
            <div className="max-w-5xl mx-auto animate-fade-in">
              <FinancialInsights />
            </div>
          )}

          {active === "briefings" && (
            <div className="max-w-7xl mx-auto animate-fade-in">
              <BriefingViewer />
            </div>
          )}

          {active === "activity" && (
            <div className="max-w-3xl mx-auto animate-fade-in">
              <ActivityFeed />
            </div>
          )}
        </main>
      </div>

      {/* Mobile bottom nav (renders below main content) */}
      <MobileNav active={active} onChange={setActive} />
    </div>
  );
}
