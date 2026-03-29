"use client";

import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from "recharts";
import { DollarSign, AlertCircle, TrendingUp, RefreshCw, WifiOff } from "lucide-react";
import clsx from "clsx";

interface Invoice {
  id: number; name: string; partner: string;
  invoice_date: string; invoice_date_due: string;
  amount_total: number; amount_residual: number;
  payment_state: string;
}

interface FinancialData {
  online:           boolean;
  weekRevenue:      number;
  totalOutstanding: number;
  totalOverdue:     number;
  overdueInvoices:  Invoice[];
  recentInvoices:   Invoice[];
  byMonth:          { month: string; invoiced: number; paid: number }[];
}

function fmt(amount: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0 }).format(amount);
}

function StatCard({ icon: Icon, label, value, sub, color }: {
  icon: React.ElementType; label: string; value: string; sub?: string; color: string;
}) {
  return (
    <div className="rounded-xl border border-heagent-border bg-heagent-deep p-4 space-y-2">
      <div className="flex items-center gap-2">
        <Icon className={clsx("w-4 h-4", color)} aria-hidden />
        <span className="text-xs text-slate-500">{label}</span>
      </div>
      <p className={clsx("text-2xl font-bold font-mono", color)}>{value}</p>
      {sub && <p className="text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean; payload?: Array<{ value: number; name: string; color: string }>; label?: string;
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-heagent-border bg-heagent-surface p-3 text-xs shadow-lg">
      <p className="font-medium text-white mb-2">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="font-mono" style={{ color: p.color }}>
          {p.name}: {fmt(p.value)}
        </p>
      ))}
    </div>
  );
};

export function FinancialInsights() {
  const [data, setData]     = useState<FinancialData | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const res = await fetch("/api/odoo", { cache: "no-store" });
      if (res.ok) setData(await res.json());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 300_000); // 5 min
    return () => clearInterval(interval);
  }, []);

  if (!data && loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-white">Financial Insights</h2>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-24 rounded-xl bg-heagent-deep animate-pulse" />)}
        </div>
        <div className="h-56 rounded-xl bg-heagent-deep animate-pulse" />
      </div>
    );
  }

  if (data && !data.online) {
    return (
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-white">Financial Insights</h2>
        <div className="card flex flex-col items-center py-12 gap-3">
          <WifiOff className="w-10 h-10 text-heagent-offline" aria-hidden />
          <p className="text-sm font-medium text-white">Odoo Offline</p>
          <p className="text-xs text-slate-500 text-center max-w-xs">
            Connect Odoo at <code className="text-heagent-cyan">{process.env.NEXT_PUBLIC_ODOO_URL ?? "http://localhost:8069"}</code> to enable financial tracking.
          </p>
          <button onClick={load} className="btn-ghost text-xs mt-2">
            <RefreshCw className="w-3.5 h-3.5" aria-hidden /> Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-white">Financial Insights</h2>
          <p className="text-xs text-slate-500">
            Live from Odoo ERP &nbsp;·&nbsp;
            <span className="text-heagent-online">Connected</span>
          </p>
        </div>
        <button onClick={load} disabled={loading} aria-label="Refresh financial data" className="btn-ghost px-2 py-2">
          <RefreshCw className={clsx("w-4 h-4 text-slate-400", loading && "animate-spin")} aria-hidden />
        </button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard icon={TrendingUp}  label="This Week"      value={fmt(data.weekRevenue)}      sub="Posted invoices" color="text-heagent-online" />
        <StatCard icon={DollarSign}  label="Outstanding"    value={fmt(data.totalOutstanding)}  sub="Not yet paid"    color="text-heagent-info" />
        <StatCard icon={AlertCircle} label="Overdue"        value={fmt(data.totalOverdue)}      sub={`${data.overdueInvoices.length} invoice(s)`} color="text-heagent-offline" />
      </div>

      {/* Bar chart: Invoiced by Month */}
      {data.byMonth.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-medium text-slate-300 mb-4">Invoiced by Month</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.byMonth} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1E3A5F" vertical={false} />
              <XAxis dataKey="month" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} width={48} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
              <Bar dataKey="invoiced" name="Invoiced" fill="#06B6D4" radius={[4, 4, 0, 0]} />
              <Bar dataKey="paid"     name="Paid"     fill="#10B981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Overdue invoices table */}
      {data.overdueInvoices.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-medium text-heagent-offline mb-3 flex items-center gap-1.5">
            <AlertCircle className="w-4 h-4" aria-hidden />
            Overdue Invoices ({data.overdueInvoices.length})
          </h3>
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-heagent-border">
                  {["Reference", "Partner", "Due Date", "Outstanding"].map((h) => (
                    <th key={h} className="text-left py-2 px-3 text-slate-500 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.overdueInvoices.map((inv) => (
                  <tr key={inv.id} className="border-b border-heagent-border/50 hover:bg-heagent-deep/50">
                    <td className="py-2 px-3 font-mono text-heagent-cyan">{inv.name}</td>
                    <td className="py-2 px-3 text-slate-300">{inv.partner}</td>
                    <td className="py-2 px-3 text-heagent-offline">{inv.invoice_date_due}</td>
                    <td className="py-2 px-3 font-mono font-medium text-white">{fmt(inv.amount_residual)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
