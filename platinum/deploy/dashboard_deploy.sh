#!/bin/bash
#===============================================================================
# PLATINUM PHASE 1C: Next.js Dashboard Deployment Script
# Purpose: Deploy Heagent Dashboard to Oracle Cloud VM with production build
# Target: Oracle Cloud Free Tier VM (Ubuntu 24.04 LTS)
#===============================================================================

set -e

echo "=============================================="
echo "  PLATINUM PHASE 1C: Dashboard Deployment"
echo "=============================================="
echo ""

#-------------------------------------------------------------------------------
# Configuration
#-------------------------------------------------------------------------------
read -p "Enter your VM's public IP address: " VM_IP
read -p "Enter your SSH private key path: " SSH_KEY_PATH
read -p "Enter your domain name for Dashboard (e.g., dashboard.yourdomain.com): " DASHBOARD_DOMAIN

echo ""
echo "Configuration:"
echo "  VM IP: $VM_IP"
echo "  Dashboard Domain: $DASHBOARD_DOMAIN"
echo ""

#-------------------------------------------------------------------------------
# Copy dashboard to VM
#-------------------------------------------------------------------------------
echo "[1/5] Copying Next.js dashboard to VM..."

# Sync dashboard files (excluding node_modules and .next)
rsync -avz \
  --exclude 'node_modules/' \
  --exclude '.next/' \
  --exclude '.env.local' \
  heagent-dashboard/ \
  ubuntu@"$VM_IP":~/ai_employee_vault/heagent-dashboard/

echo "  ✓ Dashboard files copied"

#-------------------------------------------------------------------------------
# Create production .env.local
#-------------------------------------------------------------------------------
echo ""
echo "[2/5] Creating production environment configuration..."

# Read Odoo credentials from Odoo deployment
read -p "Enter Odoo DB password (from platinum/odoo/.env): " ODOO_DB_PASSWORD

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << SSHCMDS
set -e

cd ~/ai_employee_vault/heagent-dashboard

# Create production .env.local
cat > .env.local << EOF
# Heagent Dashboard - Production Environment
# Generated: \$(date -Iseconds)

# Vault root path
VAULT_PATH=/home/ubuntu/ai_employee_vault

# Odoo connection (internal Docker network)
ODOO_URL=http://localhost:8069
ODOO_DB=postgres
ODOO_USER=odoo
ODOO_PASSWORD=${ODOO_DB_PASSWORD}

# PM2 for health checks
PM2_AVAILABLE=true

# Production settings
NODE_ENV=production
PORT=3000
EOF

# Set secure permissions
chmod 600 .env.local

echo "✓ Production .env.local created"

SSHCMDS

#-------------------------------------------------------------------------------
# Install dependencies and build
#-------------------------------------------------------------------------------
echo ""
echo "[3/5] Installing dependencies and building production bundle..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << SSHCMDS
set -e

cd ~/ai_employee_vault/heagent-dashboard

# Install dependencies
echo "Installing npm dependencies..."
npm ci --production

# Build production bundle
echo "Building production bundle..."
npm run build

echo "✓ Build complete"

SSHCMDS

#-------------------------------------------------------------------------------
# Update nginx configuration for dashboard
#-------------------------------------------------------------------------------
echo ""
echo "[4/5] Configuring nginx reverse proxy for dashboard..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << SSHCMDS
set -e

cd ~/ai_employee_vault/platinum/odoo

# Create nginx config for dashboard
cat > dashboard_nginx.conf << 'NGINX_CONF'
# Heagent Dashboard - nginx upstream
upstream heagent_dashboard {
    server localhost:3000;
    keepalive 32;
}

# Dashboard server block (add to main nginx.conf)
# This should be included in the main nginx.conf server block
location /dashboard {
    proxy_pass http://heagent_dashboard;
    proxy_http_version 1.1;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_cache_bypass \$http_upgrade;
    proxy_connect_timeout 60s;
    proxy_send_timeout 120s;
    proxy_read_timeout 120s;
}
NGINX_CONF

echo "✓ Dashboard nginx config created"

SSHCMDS

#-------------------------------------------------------------------------------
# Update main nginx.conf to include dashboard
#-------------------------------------------------------------------------------
echo ""
echo "[5/5] Updating main nginx configuration..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << SSHCMDS
set -e

cd ~/ai_employee_vault/platinum/odoo

# Backup original nginx.conf
cp nginx.conf nginx.conf.backup

# Add dashboard location to nginx.conf (before the closing brace of server block)
# Find the last location block and add dashboard after it
sed -i '/location \/nginx-health {/,/}/a\
\
        # Heagent Dashboard\
        location /dashboard {\
            proxy_pass http://localhost:3000;\
            proxy_http_version 1.1;\
            proxy_set_header Upgrade \$http_upgrade;\
            proxy_set_header Connection '"'"'upgrade'"'"';\
            proxy_set_header Host \$host;\
            proxy_set_header X-Real-IP \$remote_addr;\
            proxy_cache_bypass \$http_upgrade;\
        }' nginx.conf

echo "✓ Main nginx.conf updated with dashboard proxy"

# Reload nginx
docker compose restart nginx

echo "✓ nginx reloaded"

SSHCMDS

#-------------------------------------------------------------------------------
# Start dashboard with PM2
#-------------------------------------------------------------------------------
echo ""
echo "Starting dashboard with PM2..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << SSHCMDS
set -e

cd ~/ai_employee_vault

# Load Odoo password from .env
export ODOO_DB_PASSWORD=\$(grep ODOO_DB_PASSWORD platinum/odoo/.env | cut -d'=' -f2)

# Start dashboard with PM2
pm2 start ecosystem.config.js --only heagent-dashboard

# Save PM2 configuration
pm2 save

echo "✓ Dashboard started with PM2"

SSHCMDS

#-------------------------------------------------------------------------------
# Summary
#-------------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "  DASHBOARD DEPLOYMENT COMPLETE!"
echo "=============================================="
echo ""
echo "Access Dashboard at: https://${DASHBOARD_DOMAIN}/dashboard"
echo ""
echo "Note: The dashboard is accessible at the /dashboard path on your Odoo domain."
echo "      If you want a separate subdomain, update DNS and nginx config accordingly."
echo ""
echo "To view dashboard logs:"
echo "  ssh -i ${SSH_KEY_PATH} ubuntu@${VM_IP}"
echo "  pm2 logs heagent-dashboard"
echo ""
echo "To restart dashboard:"
echo "  pm2 restart heagent-dashboard"
echo ""
