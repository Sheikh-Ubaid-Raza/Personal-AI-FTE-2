"use client";

import { Activity, BarChart2, BookOpen, CheckSquare, LayoutDashboard, Moon, Sun } from "lucide-react";
import clsx from "clsx";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

interface NavItem {
  id:    string;
  label: string;
  icon:  React.ElementType;
}

const NAV: NavItem[] = [
  { id: "overview",  label: "Overview",      icon: LayoutDashboard },
  { id: "approvals", label: "Approvals",      icon: CheckSquare },
  { id: "finance",   label: "Finance",        icon: BarChart2 },
  { id: "briefings", label: "CEO Briefings",  icon: BookOpen },
  { id: "activity",  label: "Activity Feed",  icon: Activity },
];

interface SidebarProps {
  active:   string;
  onChange: (id: string) => void;
}

export function Sidebar({ active, onChange }: SidebarProps) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <aside className="flex flex-col h-full bg-heagent-deep border-r border-heagent-border w-64 shrink-0">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-heagent-border">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-heagent-cyan to-heagent-purple
                          flex items-center justify-center shrink-0 shadow-glow-cyan">
            <span className="text-white font-bold text-sm font-mono">H</span>
          </div>
          <div>
            <p className="text-sm font-bold text-white tracking-tight">Heagent</p>
            <p className="text-xs text-slate-500">AI Employee Dashboard</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-3 space-y-1" aria-label="Main navigation">
        {NAV.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onChange(id)}
            aria-current={active === id ? "page" : undefined}
            className={clsx(
              "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium",
              "transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-heagent-cyan",
              active === id
                ? "bg-heagent-cyan/15 text-heagent-cyan border border-heagent-cyan/20"
                : "text-slate-400 hover:bg-heagent-surface hover:text-white"
            )}
          >
            <Icon className="w-4 h-4 shrink-0" aria-hidden />
            {label}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-heagent-border space-y-2">
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Toggle theme"
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-400
                     hover:bg-heagent-surface hover:text-white transition-colors duration-150"
        >
          {/* Render only after mount to avoid SSR/client theme mismatch */}
          {mounted && (theme === "dark"
            ? <Sun  className="w-4 h-4 shrink-0" aria-hidden />
            : <Moon className="w-4 h-4 shrink-0" aria-hidden />
          )}
          {mounted ? (theme === "dark" ? "Light Mode" : "Dark Mode") : "Theme"}
        </button>
        <div className="px-3 py-2 rounded-lg bg-heagent-void border border-heagent-border/50">
          <p className="text-xs text-slate-600 font-mono">Gold Tier · claude-sonnet-4-6</p>
          <p className="text-xs text-slate-700 mt-0.5 truncate">v1.0.0 · 2026-03-08</p>
        </div>
      </div>
    </aside>
  );
}

// Mobile bottom nav (shown on small screens)
export function MobileNav({ active, onChange }: SidebarProps) {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around
                 bg-heagent-deep/95 backdrop-blur-xl border-t border-heagent-border
                 px-2 py-2 lg:hidden"
      aria-label="Mobile navigation"
    >
      {NAV.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          aria-current={active === id ? "page" : undefined}
          aria-label={label}
          className={clsx(
            "flex flex-col items-center gap-1 px-3 py-1.5 rounded-lg min-w-[44px] min-h-[44px] justify-center",
            "transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-heagent-cyan",
            active === id ? "text-heagent-cyan" : "text-slate-500"
          )}
        >
          <Icon className="w-5 h-5" aria-hidden />
          <span className="text-xs font-medium">{label}</span>
        </button>
      ))}
    </nav>
  );
}
