# Platinum Phase 1: Deployment Guide

## Overview

This guide walks you through deploying your AI Employee to Oracle Cloud Free Tier for 24/7 operation.

**Phase 1A:** Cloud VM Infrastructure Setup (4-6 hours)
**Phase 1B:** Odoo Community Deployment with HTTPS (6-8 hours)
**Phase 1C:** Heagent Dashboard Deployment (2-3 hours) ← **NEW**

---

## Prerequisites

1. **Oracle Cloud Account** - Free tier account at https://cloud.oracle.com/
2. **Domain Name** - For Odoo HTTPS (e.g., odoo.yourdomain.com)
3. **SSH Key Pair** - For VM access
4. **Local Project** - This vault with all Gold Tier components working

---

## Phase 1A: Cloud VM Infrastructure Setup

### Step 1: Create Oracle Cloud VM

1. Log in to [Oracle Cloud Console](https://cloud.oracle.com/)
2. Navigate to: **Compute → Instances → Create Instance**
3. Configure:
   - **Name:** `ai-employee-cloud-vm`
   - **Image:** Ubuntu 24.04 LTS
   - **Shape:** VM.Standard.A1.Flex (ARM Ampere)
   - **OCPUs:** 4
   - **Memory:** 24 GB
   - **Boot Volume:** 200 GB
4. Note the **Public IP address**

### Step 2: Configure Network Security Groups

Before running the setup script, configure Oracle Cloud NSGs:

1. Go to: **Networking → Virtual Cloud Networks**
2. Click your VCN → **Security Lists → Default Security List**
3. Add **Ingress Rules**:

| Source    | Protocol | Port Range | Purpose          |
|-----------|----------|------------|------------------|
| 0.0.0.0/0 | TCP      | 22         | SSH              |
| 0.0.0.0/0 | TCP      | 80         | HTTP             |
| 0.0.0.0/0 | TCP      | 443        | HTTPS            |
| 0.0.0.0/0 | TCP      | 8069       | Odoo (optional)  |

### Step 3: Run VM Setup Script

```bash
# Make script executable
chmod +x platinum/deploy/oracle_cloud_setup.sh

# Run setup
./platinum/deploy/oracle_cloud_setup.sh
```

**The script will:**
- Install Python 3.13, Node.js v24, PM2
- Install Google Chrome (headless for Playwright)
- Install Git, nginx, certbot
- Install Docker + Docker Compose
- Configure firewall (ufw)
- Create directory structure

### Step 4: Copy Project Files to VM

```bash
# Sync your vault to the VM (excluding secrets)
rsync -avz \
  --exclude '.env' \
  --exclude '*.session/' \
  --exclude '.gmail-credentials/' \
  --exclude 'node_modules/' \
  --exclude '.git/' \
  /path/to/local/vault/ \
  ubuntu@<VM_IP>:~/ai_employee_vault/
```

### Step 5: Configure PM2 Watchers

```bash
# SSH into VM
ssh -i <key> ubuntu@<VM_IP>

# Navigate to vault
cd ~/ai_employee_vault

# Copy PM2 config
cp platinum/deploy/ecosystem.config.js ./ecosystem.config.js

# Install Python dependencies
pip install watchdog google-api-python-client playwright

# Install Playwright browsers
playwright install chromium

# Start watchers with PM2
pm2 start ecosystem.config.js

# Save PM2 configuration
pm2 save

# Enable PM2 startup on boot
pm2 startup
# Run the command it outputs
```

### Step 6: Verify Watchers

```bash
# Check PM2 status
pm2 status

# View logs
pm2 logs gmail-watcher
pm2 logs filesystem-watcher
pm2 logs orchestrator-cloud
```

---

## Phase 1C: Heagent Dashboard Deployment

### Step 1: Copy Dashboard to VM

```bash
# Sync dashboard files (excluding node_modules and .next)
rsync -avz \
  --exclude 'node_modules/' \
  --exclude '.next/' \
  --exclude '.env.local' \
  heagent-dashboard/ \
  ubuntu@<VM_IP>:~/ai_employee_vault/heagent-dashboard/
```

### Step 2: Configure Environment

```bash
# SSH into VM
ssh -i <key> ubuntu@<VM_IP>

# Navigate to dashboard
cd ~/ai_employee_vault/heagent-dashboard

# Create production .env.local
cat > .env.local << EOF
# Production Environment
VAULT_PATH=/home/ubuntu/ai_employee_vault
ODOO_URL=http://localhost:8069
ODOO_DB=postgres
ODOO_USER=odoo
ODOO_PASSWORD=<from_platinum_odoo_.env>
PM2_AVAILABLE=true
NODE_ENV=production
PORT=3000
EOF

# Set secure permissions
chmod 600 .env.local
```

### Step 3: Install Dependencies and Build

```bash
# Install production dependencies
npm ci --production

# Build production bundle
npm run build
```

### Step 4: Start with PM2

```bash
# Navigate to vault root
cd ~/ai_employee_vault

# Load Odoo password
export ODOO_DB_PASSWORD=$(grep ODOO_DB_PASSWORD platinum/odoo/.env | cut -d'=' -f2)

# Start dashboard with PM2
pm2 start ecosystem.config.js --only heagent-dashboard

# Save PM2 configuration
pm2 save
```

### Step 5: Configure nginx Proxy

The nginx configuration already includes dashboard proxy rules. Just reload nginx:

```bash
# Reload nginx to pick up dashboard config
docker compose restart nginx
```

### Step 6: Access Dashboard

Open your browser:
```
https://your-domain.com/dashboard
```

**Dashboard Features:**
- 📊 Service Health Grid (PM2, Odoo, Watchers)
- ✅ Approvals Tab (Plan_*.md files)
- 💰 Finance Tab (Odoo revenue, invoices, overdue)
- 📈 CEO Briefings (Weekly reports)
- 📜 Activity Feed (Real-time logs)

---

## Phase 1B: Odoo Community Deployment

### Step 1: Configure Domain DNS

Point your domain to the VM:

```
Type: A
Name: @ (or odoo for subdomain)
Value: <VM_PUBLIC_IP>
TTL: 3600
```

Wait 5-10 minutes for DNS propagation.

### Step 2: Run Odoo Deployment Script

```bash
# Make script executable
chmod +x platinum/deploy/odoo_deploy.sh

# Run deployment
./platinum/deploy/odoo_deploy.sh
```

**You'll need:**
- VM Public IP
- SSH key path
- Domain name (e.g., odoo.yourdomain.com)

**The script will:**
- Copy Docker compose files
- Generate secure passwords
- Start Odoo + PostgreSQL + nginx
- Obtain Let's Encrypt SSL certificate
- Verify deployment

### Step 3: Save Credentials

After deployment, save these securely:

```bash
# View credentials
ssh -i <key> ubuntu@<VM_IP>
cat ~/ai_employee_vault/platinum/odoo/.env
```

**Save:**
- `ODOO_DB_PASSWORD`
- `ODOO_ADMIN_PASSWORD`

### Step 4: Configure Odoo

1. Open browser: `https://your-domain.com`
2. Login with admin credentials
3. Create database:
   - Database Name: `postgres`
   - Email: your email
   - Password: admin password from .env
4. Install required apps:
   - Invoicing
   - Contacts

### Step 5: Update Local Odoo MCP Config

Update your local `.env` file:

```bash
# Cloud Odoo Configuration
ODOO_URL=https://your-domain.com
ODOO_DB=postgres
ODOO_USER=odoo
ODOO_PASSWORD=<from_cloud_.env>
```

Update MCP config (`.mcp.json`):

```json
{
  "mcpServers": {
    "odoo-cloud": {
      "command": "node",
      "args": [".claude/mcp-servers/odoo-mcp/server.js"],
      "env": {
        "ODOO_URL": "https://your-domain.com",
        "ODOO_DB": "postgres",
        "ODOO_USER": "odoo",
        "ODOO_PASSWORD": "<password>",
        "DRAFT_ONLY": "true"
      }
    }
  }
}
```

### Step 6: Test Cloud Odoo Connection

```bash
# SSH into VM
ssh -i <key> ubuntu@<VM_IP>

# Test Odoo health
curl https://your-domain.com/web/health

# Test MCP connection
cd ~/ai_employee_vault
python -c "from .claude.mcp-servers.odoo-mcp.server import odoo_test_connection; print(odoo_test_connection())"
```

---

## Monitoring & Maintenance

### PM2 Commands

```bash
# Status
pm2 status

# Logs
pm2 logs

# Restart all
pm2 restart all

# Restart specific
pm2 restart gmail-watcher

# Stop all
pm2 stop all

# Delete all
pm2 delete all
```

### Docker Commands

```bash
# Container status
docker compose ps

# View logs
docker compose logs -f odoo
docker compose logs -f nginx

# Restart Odoo
docker compose restart odoo

# View resource usage
docker stats
```

### Backup Verification

```bash
# Check backup directory
ls -la ~/ai_employee_vault/platinum/backups/

# View latest backup log
cat ~/ai_employee_vault/platinum/backups/backup_*.log | tail -50
```

### Health Monitoring

```bash
# Check Odoo health endpoint
curl https://your-domain.com/web/health

# Check nginx health
curl https://your-domain.com/nginx-health

# View health logs
cat ~/ai_employee_vault/Logs/odoo_health.jsonl | tail -20
```

---

## Troubleshooting

### Issue: PM2 watchers not starting

```bash
# Check Python version
python3 --version

# Reinstall dependencies
pip install -r requirements.txt

# Check PM2 logs
pm2 logs --lines 100
```

### Issue: Odoo container won't start

```bash
# View Odoo logs
docker compose logs odoo

# Check PostgreSQL is running
docker compose ps db

# Restart all containers
docker compose down
docker compose up -d
```

### Issue: SSL certificate failed

```bash
# Check port 80 is open
sudo ufw status

# Check nginx is running
docker compose ps nginx

# Retry certbot
docker run --rm -it \
  -v /etc/letsencrypt:/etc/letsencrypt \
  certbot/certbot renew
```

### Issue: Can't access Odoo via HTTPS

1. Check DNS propagation: `nslookup your-domain.com`
2. Check firewall: `sudo ufw status`
3. Check Oracle Cloud NSG rules
4. Check nginx logs: `docker compose logs nginx`

---

## Security Checklist

- [ ] SSH key permissions: `chmod 600 <key>`
- [ ] Firewall enabled with minimal rules
- [ ] Odoo accessed only via HTTPS
- [ ] Strong passwords in .env
- [ ] .env file permissions: `chmod 600 .env`
- [ ] Regular backups configured
- [ ] PM2 auto-restart on boot enabled
- [ ] Docker containers set to `restart: unless-stopped`

---

## Next Steps

After completing Phase 1:

1. **Phase 2:** Implement Secure Vault Sync & Delegation
   - Git-based sync between Cloud and Local
   - Claim-by-move workflow
   - Security audit script

2. **Phase 3:** Work-Zone Specialization
   - Cloud: Draft-only mode
   - Local: Final approval and execution
   - Platinum Demo gate test

---

## Cost Estimate

**Oracle Cloud Free Tier:**
- 2 VMs (ARM Ampere, 4 OCPUs, 24GB RAM each) - **FREE**
- 200 GB boot volume per VM - **FREE**
- Object Storage for backups (optional) - Up to 10GB FREE

**Total Monthly Cost: $0** (within free tier limits)

---

## Support

For issues or questions:
- Check logs: `pm2 logs`, `docker compose logs`
- Review documentation: `Company_Handbook.md`
- Wednesday Research Meeting: Zoom link in hackathon doc
