# Platinum Tier Implementation

## Overview

This directory contains all files for **Platinum Tier** deployment - transforming your local AI Employee into a production-grade, always-on cloud system.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLOUD VM (Oracle/AWS)                    │
│  24/7 Always-On, HTTPS, Backed Up                           │
├─────────────────────────────────────────────────────────────┤
│  • Gmail Watcher (draft replies only)                       │
│  • Filesystem Watcher (draft-only)                          │
│  • Orchestrator (Cloud instance - DRAFT_ONLY mode)          │
│  • Heagent Dashboard (Next.js UI on /dashboard)             │
│  • Odoo Community (HTTPS via nginx + Let's Encrypt)         │
│  • Odoo MCP (draft invoices only, no posting)               │
│  • Health Monitoring (auto-restart on failure)              │
│  • Daily Backups (database + filestore)                     │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ Vault Sync (Git/Syncthing) - Phase 2
                          │ ONLY: .md files, NO secrets
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    LOCAL MACHINE (Your Laptop)              │
│  Human-Present, Secure, Final Actions                       │
├─────────────────────────────────────────────────────────────┤
│  • Human Approval (tick checkbox in Plan files)             │
│  • WhatsApp Session (.wa_session/ — LOCAL ONLY)             │
│  • Banking Credentials (NEVER sync)                         │
│  • OAuth Tokens for Gmail (NEVER sync)                      │
│  • Final Send Actions (Gmail MCP, Social publish)           │
│  • Dashboard.md (Local owns master)                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
platinum/
├── deploy/                      # Deployment scripts & guides
│   ├── oracle_cloud_setup.sh    # Phase 1A: VM initialization
│   ├── firewall_config.sh       # Phase 1A: Firewall rules
│   ├── odoo_deploy.sh           # Phase 1B: Odoo deployment
│   ├── ecosystem.config.js      # PM2 process configuration
│   ├── test_phase1.py           # Phase 1 verification tests
│   └── DEPLOYMENT_GUIDE.md      # Step-by-step guide
├── odoo/                        # Odoo Community deployment
│   ├── docker-compose.yml       # Odoo + PostgreSQL + nginx
│   ├── nginx.conf               # HTTPS reverse proxy
│   ├── backup_script.sh         # Daily backup automation
│   ├── health_check.py          # Health monitoring
│   └── .env.example             # Environment template
├── config/                      # Configuration files
│   ├── mcp-cloud-odoo.json      # Cloud Odoo MCP config
│   ├── cloud_agent_config.json  # Cloud agent restrictions (Phase 3)
│   └── local_agent_config.json  # Local agent capabilities (Phase 3)
└── sync/                        # Vault sync scripts (Phase 2)
    ├── sync_manager.py          # Git-based sync automation
    └── security_audit.py        # Secret leak detection
```

---

## Phases

### Phase 1: Cloud Infrastructure (Current)

**1A: Cloud VM Setup** (4-6 hours)
- Oracle Cloud Free Tier VM provisioning
- Ubuntu 24.04 LTS with Python 3.13, Node.js v24
- PM2 for 24/7 process management
- Headless Chrome for Playwright
- Firewall configuration

**1B: Odoo Community Deployment** (6-8 hours)
- Docker Compose stack (Odoo + PostgreSQL + nginx + certbot)
- HTTPS with Let's Encrypt
- Daily automated backups
- Health monitoring with auto-restart
- Cloud Agent integration (draft-only mode)

**Files Created:**
- `deploy/oracle_cloud_setup.sh`
- `deploy/firewall_config.sh`
- `deploy/ecosystem.config.js`
- `odoo/docker-compose.yml`
- `odoo/nginx.conf`
- `odoo/backup_script.sh`
- `odoo/health_check.py`
- `deploy/odoo_deploy.sh`
- `config/mcp-cloud-odoo.json`
- `deploy/test_phase1.py`
- `deploy/DEPLOYMENT_GUIDE.md`

---

### Phase 2: Secure Vault Sync & Delegation (Next)

**Objective:** Establish secure communication between Cloud and Local agents.

**Tasks:**
- Git-based sync with auto-commit every 5 minutes
- Security boundaries (`.env`, sessions, tokens NEVER sync)
- Claim-by-move rule implementation
- Security audit script

**Files To Create:**
- `sync/sync_manager.py`
- `sync/security_audit.py`
- Updated `.gitignore`
- Updated `orchestrator.py` (claim-by-move logic)

---

### Phase 3: Work-Zone Specialization & Demo

**Objective:** Enforce domain ownership and pass Platinum Demo gate.

**Tasks:**
- Cloud specialization: Email triage + Social drafts (draft-only)
- Local specialization: Approvals + WhatsApp + Banking + Final send
- A2A upgrade (optional): Direct agent-to-agent messages
- Platinum Demo gate test

**Files To Create:**
- `config/cloud_agent_config.json`
- `config/local_agent_config.json`
- `test_platinum_demo.py`

---

## Quick Start

### Phase 1 Deployment

```bash
# 1. Create Oracle Cloud VM (manual - see DEPLOYMENT_GUIDE.md)

# 2. Run VM setup script
chmod +x platinum/deploy/oracle_cloud_setup.sh
./platinum/deploy/oracle_cloud_setup.sh

# 3. Configure firewall
chmod +x platinum/deploy/firewall_config.sh
./platinum/deploy/firewall_config.sh

# 4. Deploy Odoo Community
chmod +x platinum/deploy/odoo_deploy.sh
./platinum/deploy/odoo_deploy.sh

# 5. Verify deployment
python3 platinum/deploy/test_phase1.py
```

---

## Security Rules

### NEVER Sync to Cloud

The following files/directories MUST remain local-only:

```
.env
*.session/
.gmail-credentials/
*_token.json
mcp-*.json (with secrets)
```

### Cloud Agent Restrictions

Cloud agent operates in **DRAFT-ONLY** mode:

- ✅ Can read emails, create draft replies
- ✅ Can create social post drafts
- ✅ Can create draft invoices in Odoo
- ❌ Cannot send emails
- ❌ Cannot publish social posts
- ❌ Cannot post invoices/payments
- ❌ Cannot access WhatsApp

### Local Agent Capabilities

Local agent has **final action** authority:

- ✅ Approve/reject Cloud drafts
- ✅ Send emails via Gmail MCP
- ✅ Publish social posts
- ✅ Post invoices/payments in Odoo
- ✅ Access WhatsApp sessions
- ✅ Access banking credentials

---

## Monitoring

### PM2 (Watchers & Orchestrator)

```bash
# Status
pm2 status

# Logs
pm2 logs

# Restart
pm2 restart all
```

### Docker (Odoo Stack)

```bash
# Status
docker compose ps

# Logs
docker compose logs -f odoo

# Restart
docker compose restart
```

### Health Checks

```bash
# Odoo health
curl https://your-domain.com/web/health

# nginx health
curl https://your-domain.com/nginx-health
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| PM2 processes exit | Check logs: `pm2 logs`, reinstall deps |
| Odoo won't start | Check PostgreSQL: `docker compose ps db` |
| SSL cert failed | Verify DNS, check port 80 open |
| Can't access HTTPS | Check firewall, NSG rules, nginx logs |

### Log Locations

```
~/ai_employee_vault/platinum/logs/    # PM2 watcher logs
~/ai_employee_vault/Logs/             # Audit logs, health logs
/var/log/odoo_health_monitor.log      # Health monitor
~/ai_employee_vault/platinum/backups/ # Backup logs
```

---

## Cost Estimate

**Oracle Cloud Free Tier:**
- 2x VM.Standard.A1.Flex (4 OCPUs, 24GB RAM) - **FREE**
- 2x 200GB boot volumes - **FREE**
- Object Storage for backups (10GB) - **FREE**

**Total: $0/month** (within free tier limits)

---

## Next Steps

1. **Complete Phase 1** deployment using `DEPLOYMENT_GUIDE.md`
2. **Run verification tests:** `python3 platinum/deploy/test_phase1.py`
3. **Proceed to Phase 2:** Implement vault sync & delegation
4. **Complete Phase 3:** Work-zone specialization & demo gate

---

## References

- Hackathon Document: `Personal AI Employee Hackathon 0_ Building Autonomous FTEs in 2026 (2).md`
- Project Report: `PROJECT_REPORT.md`
- Platinum Breakdown: `PLATINUM_TIER_BREAKDOWN.md`
- Deployment Guide: `platinum/deploy/DEPLOYMENT_GUIDE.md`

---

**Status:** Phase 1 Complete ✅ | Phase 2 Pending | Phase 3 Pending
