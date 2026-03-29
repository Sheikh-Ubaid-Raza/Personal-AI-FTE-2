# Heagent Dashboard UI

Modern Next.js control panel for the **Personal AI Employee** system (Gold Tier).
Connects to the local Obsidian vault filesystem and Odoo 19 Community via JSON-RPC.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 15 (App Router, Turbopack) |
| Styling | Tailwind CSS 3 + custom Heagent design system |
| Components | Shadcn/UI conventions, Lucide icons |
| Charts | Recharts 2 |
| Markdown | react-markdown + remark-gfm |
| Themes | next-themes (dark/light toggle) |
| Data | Local filesystem (vault) + Odoo JSON-RPC |

---

## Quick Start

### 1. Install dependencies

```bash
cd heagent-dashboard
npm install
```

### 2. Configure environment

Edit `.env.local` and fill in your Odoo password:

```env
VAULT_PATH=/mnt/c/h-0/AI_Employee_Vault_bronze
ODOO_URL=http://172.31.192.1:8069
ODOO_DB=Social_Accounting
ODOO_USER=ubaidkamal420@gmail.com
ODOO_PASSWORD=<your_odoo_password>
```

> All variables are server-side only — never exposed to the browser.

### 3. Run the dev server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### 4. Run alongside Claude Code

The dashboard is a **read-mostly** companion — it never interferes with Claude Code.
Run them side-by-side:

```bash
# Terminal 1 — Claude Code (vault orchestration)
cd /mnt/c/h-0/AI_Employee_Vault_bronze
claude

# Terminal 2 — Heagent Dashboard
cd /mnt/c/h-0/AI_Employee_Vault_bronze/heagent-dashboard
npm run dev
```

Both share the same vault directory. The dashboard polls vault files every 15–30 seconds and reflects all changes made by Claude Code in real time.

---

## Features

### Overview Tab
- **Service Health Grid** — 8 service cards with live 🟢/🔴 status
  - Orchestrator, Gmail Watcher, File Watcher (via `pm2 jlist`)
  - Odoo ERP (JSON-RPC ping)
  - LinkedIn, Facebook, Instagram, Twitter (session config status)
- **Ralph Wiggum Loop** — Progress bar showing iteration `N/5`, pending tasks list
- **Live Activity Feed** — Last 20 log events, auto-refreshes every 15s

### Approvals Tab
- Lists every `Plan_*.md` in `Needs_Approval/`
- **View Plan** button expands the full markdown plan
- **Approve** button writes `- [x] **Approve Action:**` directly to the file
- Risk-level color coding: 🔴 High / 🟡 Medium / 🔵 Low
- Auto-refreshes every 20s — new tasks appear automatically

### Finance Tab
- Requires Odoo to be online
- **KPI Cards** — Week Revenue, Total Outstanding, Total Overdue
- **Bar Chart** — Invoiced vs Paid by month (last 6 months, Recharts)
- **Overdue Table** — Partner, due date, outstanding amount
- Shows `Odoo Offline` gracefully when Odoo is unreachable

### CEO Briefings Tab
- Lists all `Briefings/Briefing_*.md` files (newest first)
- Renders full markdown with GFM support (tables, code blocks, checklists)
- Shows task count and Odoo connectivity per briefing

### Activity Feed Tab
- Real-time stream of `Logs/YYYY-MM-DD.json` entries
- Color-coded by actor (orchestrator, ralph-wiggum, social media skills, etc.)
- New entries flash cyan on arrival
- `formatDistanceToNow` relative timestamps

---

## API Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/api/health` | GET | PM2 status + Odoo ping + vault counts |
| `/api/approvals` | GET | List `Needs_Approval/*.md` with parsed metadata |
| `/api/approve` | POST `{ filename }` | Write `[x]` checkbox to approval file |
| `/api/activity` | GET `?limit=N` | Last N log entries from `Logs/` |
| `/api/briefings` | GET | List briefings; `?file=X.md` returns full content |
| `/api/odoo` | GET | Financial data: invoices, revenue, overdue (cached 5 min) |
| `/api/ralph` | GET | Ralph Wiggum state + vault folder counts |

---

## Design System (Heagent Brand)

**"Futuristic Healthcare"** — dark navy surfaces, cyan/teal primary, purple accent.

```
Void      #050B18   — page background
Deep      #0A1628   — card interior
Surface   #0F2340   — panel background
Border    #1E3A5F   — borders / dividers
Cyan      #06B6D4   — primary brand / links
Blue      #0EA5E9   — secondary accent
Purple    #7C3AED   — accent / graphs
Online    #10B981   — success / running
Offline   #EF4444   — error / stopped
Warn      #F59E0B   — warning / looping
Info      #3B82F6   — informational
```

**Accessibility:**
- All contrast ratios ≥ 4.5:1 (WCAG AA)
- Minimum 44×44px touch targets on all buttons
- `aria-label` on all icon-only buttons
- Visible focus rings (2px cyan outline)
- `prefers-reduced-motion` respected via CSS

---

## Production Build

```bash
npm run build
npm start
```

Or add to PM2:

```bash
pm2 start npm --name "heagent-ui" -- start
pm2 save
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `pm2 jlist` empty | Ensure PM2 is installed globally: `npm install -g pm2` |
| Odoo shows offline | Check `ODOO_URL` / `ODOO_PASSWORD` in `.env.local` |
| Vault files not found | Confirm `VAULT_PATH` is the absolute path to your vault |
| Port 3000 in use | `npm run dev -- -p 3001` |
| `react-markdown` SSR error | Already handled — components use `"use client"` |

---

*Heagent Dashboard v1.0.0 — Built with Next.js 15 + Tailwind CSS*
*UI/UX: UI-UX Pro Max Skill (skills.sh/nextlevelbuilder)*
