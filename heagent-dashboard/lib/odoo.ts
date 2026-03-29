/**
 * lib/odoo.ts
 * Server-side Odoo JSON-RPC client.
 * All functions return null on failure (graceful degradation).
 */

const ODOO_URL      = (process.env.ODOO_URL      ?? "http://localhost:8069").replace(/\/$/, "");
const ODOO_DB       = process.env.ODOO_DB       ?? "";
const ODOO_USER     = process.env.ODOO_USER     ?? "";
const ODOO_PASSWORD = process.env.ODOO_PASSWORD ?? "";

let _uid: number | null = null;
let _available: boolean | null = null;

async function jsonrpc(service: string, method: string, args: unknown[]): Promise<unknown> {
  const resp = await fetch(`${ODOO_URL}/jsonrpc`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({
      jsonrpc: "2.0", method: "call", id: 1,
      params: { service, method, args },
    }),
    signal: AbortSignal.timeout(12_000),
  });
  const data = await resp.json() as { result?: unknown; error?: { message?: string; data?: { message?: string } } };
  if (data.error) {
    const msg = data.error?.data?.message ?? data.error?.message ?? "Unknown Odoo error";
    throw new Error(msg);
  }
  return data.result;
}

async function authenticate(): Promise<number | null> {
  if (_available === false) return null;
  if (_uid !== null) return _uid;
  if (!ODOO_DB || !ODOO_USER || !ODOO_PASSWORD) { _available = false; return null; }
  try {
    const uid = await jsonrpc("common", "authenticate", [ODOO_DB, ODOO_USER, ODOO_PASSWORD, {}]);
    if (!uid) { _available = false; return null; }
    _uid = uid as number;
    _available = true;
    return _uid;
  } catch {
    _available = false;
    return null;
  }
}

async function execute(
  model: string, method: string,
  args: unknown[] = [], kwargs: Record<string, unknown> = {}
): Promise<unknown | null> {
  const uid = await authenticate();
  if (uid === null) return null;
  try {
    return await jsonrpc("object", "execute_kw", [ODOO_DB, uid, ODOO_PASSWORD, model, method, args, kwargs]);
  } catch {
    return null;
  }
}

// ── Public API ────────────────────────────────────────────────────────

export interface OdooInvoice {
  id:              number;
  name:            string;
  partner:         string;
  invoice_date:    string;
  invoice_date_due:string;
  amount_total:    number;
  amount_residual: number;
  payment_state:   string;
  state:           string;
}

export interface OdooFinancialData {
  online:            boolean;
  weekRevenue:       number;
  totalOutstanding:  number;
  totalOverdue:      number;
  overdueInvoices:   OdooInvoice[];
  recentInvoices:    OdooInvoice[];
  byMonth:           { month: string; invoiced: number; paid: number }[];
}

export async function getFinancialData(): Promise<OdooFinancialData> {
  const uid = await authenticate();
  if (!uid) {
    return {
      online: false, weekRevenue: 0, totalOutstanding: 0,
      totalOverdue: 0, overdueInvoices: [], recentInvoices: [], byMonth: [],
    };
  }

  const today = new Date();
  const todayStr = today.toISOString().slice(0, 10);
  const weekAgo  = new Date(today); weekAgo.setDate(today.getDate() - 7);
  const sixMonthsAgo = new Date(today); sixMonthsAgo.setMonth(today.getMonth() - 6);

  // All posted customer invoices (last 6 months for charts)
  const raw = await execute("account.move", "search_read",
    [[
      ["move_type", "=", "out_invoice"],
      ["state",     "=", "posted"],
      ["invoice_date", ">=", sixMonthsAgo.toISOString().slice(0, 10)],
    ]],
    { fields: ["name", "partner_id", "invoice_date", "invoice_date_due", "amount_total", "amount_residual", "payment_state", "state"] }
  ) as Array<Record<string, unknown>> | null ?? [];

  const invoices: OdooInvoice[] = raw.map((inv) => ({
    id:               inv.id as number,
    name:             inv.name as string,
    partner:          Array.isArray(inv.partner_id) ? (inv.partner_id[1] as string) : "—",
    invoice_date:     (inv.invoice_date as string) ?? "",
    invoice_date_due: (inv.invoice_date_due as string) ?? "",
    amount_total:     inv.amount_total as number,
    amount_residual:  inv.amount_residual as number,
    payment_state:    inv.payment_state as string,
    state:            inv.state as string,
  }));

  // Week revenue
  const weekRevenue = invoices
    .filter((i) => i.invoice_date >= weekAgo.toISOString().slice(0, 10))
    .reduce((s, i) => s + i.amount_total, 0);

  // Outstanding & overdue
  const unpaid = invoices.filter((i) => !["paid", "reversed"].includes(i.payment_state));
  const totalOutstanding = unpaid.reduce((s, i) => s + i.amount_residual, 0);
  const overdue = unpaid.filter((i) => i.invoice_date_due && i.invoice_date_due < todayStr);
  const totalOverdue = overdue.reduce((s, i) => s + i.amount_residual, 0);

  // By-month aggregation (last 6 months)
  const monthMap: Record<string, { invoiced: number; paid: number }> = {};
  for (const inv of invoices) {
    if (!inv.invoice_date) continue;
    const month = inv.invoice_date.slice(0, 7); // YYYY-MM
    if (!monthMap[month]) monthMap[month] = { invoiced: 0, paid: 0 };
    monthMap[month].invoiced += inv.amount_total;
    if (inv.payment_state === "paid") monthMap[month].paid += inv.amount_total;
  }
  const byMonth = Object.entries(monthMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, d]) => ({ month, ...d }));

  return {
    online: true,
    weekRevenue,
    totalOutstanding,
    totalOverdue,
    overdueInvoices:  overdue.sort((a, b) => a.invoice_date_due.localeCompare(b.invoice_date_due)).slice(0, 10),
    recentInvoices:   invoices.sort((a, b) => b.invoice_date.localeCompare(a.invoice_date)).slice(0, 8),
    byMonth,
  };
}

export async function isOdooOnline(): Promise<boolean> {
  const uid = await authenticate();
  return uid !== null;
}
