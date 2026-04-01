#!/bin/bash
#===============================================================================
# PLATINUM PHASE 1B: Odoo Community Deployment Script
# Purpose: Deploy Odoo Community with HTTPS on Oracle Cloud VM
# Target: Ubuntu 24.04 LTS on Oracle Cloud Free Tier
#===============================================================================

set -e

echo "=============================================="
echo "  PLATINUM PHASE 1B: Odoo Community Deployment"
echo "=============================================="
echo ""

#-------------------------------------------------------------------------------
# Configuration
#-------------------------------------------------------------------------------
read -p "Enter your VM's public IP address: " VM_IP
read -p "Enter your SSH private key path: " SSH_KEY_PATH
read -p "Enter your domain name for Odoo (e.g., odoo.yourdomain.com): " DOMAIN

echo ""
echo "Configuration:"
echo "  VM IP: $VM_IP"
echo "  Domain: $DOMAIN"
echo ""

#-------------------------------------------------------------------------------
# Copy files to VM
#-------------------------------------------------------------------------------
echo "[1/6] Copying deployment files to VM..."

scp -i "$SSH_KEY_PATH" \
    platinum/odoo/docker-compose.yml \
    platinum/odoo/nginx.conf \
    platinum/odoo/backup_script.sh \
    platinum/odoo/health_check.py \
    ubuntu@"$VM_IP":~/ai_employee_vault/platinum/odoo/

echo "  ✓ Files copied"

#-------------------------------------------------------------------------------
# Create directories and .env file
#-------------------------------------------------------------------------------
echo ""
echo "[2/6] Creating directories and configuration..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << SSHCMDS
set -e

cd ~/ai_employee_vault/platinum/odoo

# Create directories
mkdir -p ssl custom_addons logs

# Generate random passwords
ODOO_DB_PASSWORD=\$(openssl rand -base64 32)
ODOO_ADMIN_PASSWORD=\$(openssl rand -base64 32)

# Create .env file
cat > .env << EOF
# Odoo Configuration
# Generated: \$(date -Iseconds)
ODOO_DB_PASSWORD=${ODOO_DB_PASSWORD}
ODOO_ADMIN_PASSWORD=${ODOO_ADMIN_PASSWORD}
BACKUP_RETENTION_DAYS=7

# Cloud Agent Configuration
ODOO_URL=http://localhost:8069
ODOO_DB=postgres
ODOO_USER=odoo
ODOO_PASSWORD=\${ODOO_DB_PASSWORD}
EOF

# Set secure permissions on .env
chmod 600 .env

# Create nginx ssl directory
mkdir -p ssl

echo "✓ Directories and .env created"
echo "  IMPORTANT: Save these passwords securely!"
echo "  DB Password: ${ODOO_DB_PASSWORD}"
echo "  Admin Password: ${ODOO_ADMIN_PASSWORD}"

SSHCMDS

#-------------------------------------------------------------------------------
# Update nginx.conf with domain
#-------------------------------------------------------------------------------
echo ""
echo "[3/6] Configuring nginx for domain..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << SSHCMDS
set -e

cd ~/ai_employee_vault/platinum/odoo

# Replace domain placeholder in nginx.conf
sed -i "s/your-domain.com/${DOMAIN}/g" nginx.conf

echo "✓ nginx configured for domain: ${DOMAIN}"

SSHCMDS

#-------------------------------------------------------------------------------
# Start Docker containers
#-------------------------------------------------------------------------------
echo ""
echo "[4/6] Starting Docker containers..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << SSHCMDS
set -e

cd ~/ai_employee_vault/platinum/odoo

# Pull images
echo "Pulling Docker images..."
docker compose pull

# Start containers
echo "Starting containers..."
docker compose up -d

# Wait for Odoo to be ready
echo "Waiting for Odoo to initialize (this may take 2-3 minutes)..."
sleep 60

# Check container status
docker compose ps

echo "✓ Containers started"

SSHCMDS

#-------------------------------------------------------------------------------
# Obtain SSL Certificate
#-------------------------------------------------------------------------------
echo ""
echo "[5/6] Obtaining Let's Encrypt SSL certificate..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << SSHCMDS
set -e

cd ~/ai_employee_vault/platinum/odoo

# Stop nginx temporarily to free port 80
docker stop odoo_nginx || true

# Get SSL certificate using standalone certbot
docker run --rm -it \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v /var/www/certbot:/var/www/certbot \
    certbot/certbot certonly \
    --standalone \
    --agree-tos \
    --non-interactive \
    --email admin@${DOMAIN} \
    -d ${DOMAIN} \
    --preferred-challenges http

# Restart nginx
docker start odoo_nginx || docker compose up -d nginx

echo "✓ SSL certificate obtained"

SSHCMDS

#-------------------------------------------------------------------------------
# Verify deployment
#-------------------------------------------------------------------------------
echo ""
echo "[6/6] Verifying deployment..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << SSHCMDS
set -e

cd ~/ai_employee_vault/platinum/odoo

echo "Container Status:"
docker compose ps

echo ""
echo "Testing Odoo health endpoint..."
curl -s http://localhost:8069/web/health | head -20 || echo "Health check pending..."

echo ""
echo "Testing nginx..."
curl -s -I http://localhost:80 | head -5 || echo "nginx pending..."

echo ""
echo "✓ Deployment verification complete"

SSHCMDS

#-------------------------------------------------------------------------------
# Summary
#-------------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "  ODOO COMMUNITY DEPLOYMENT COMPLETE!"
echo "=============================================="
echo ""
echo "Access Odoo at: https://${DOMAIN}"
echo ""
echo "IMPORTANT: Save your credentials from the .env file:"
echo "  Location: ~/ai_employee_vault/platinum/odoo/.env"
echo ""
echo "To view logs:"
echo "  ssh -i ${SSH_KEY_PATH} ubuntu@${VM_IP}"
echo "  cd ~/ai_employee_vault/platinum/odoo"
echo "  docker compose logs -f odoo"
echo ""
echo "Next Steps:"
echo "  1. Update your local .env with cloud Odoo credentials"
echo "  2. Configure Odoo MCP server to connect to cloud instance"
echo "  3. Set up health monitoring via PM2"
echo ""
