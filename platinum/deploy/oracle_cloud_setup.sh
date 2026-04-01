#!/bin/bash
#===============================================================================
# PLATINUM PHASE 1A: Oracle Cloud VM Initialization Script
# Purpose: Set up Ubuntu 24.04 LTS VM with all required dependencies
# Target: Oracle Cloud Free Tier (ARM Ampere A1 Compute)
#===============================================================================

set -e  # Exit on error

echo "=============================================="
echo "  PLATINUM PHASE 1A: Oracle Cloud VM Setup"
echo "=============================================="
echo ""

#-------------------------------------------------------------------------------
# VM Creation Instructions (Manual - Run in Oracle Cloud Console)
#-------------------------------------------------------------------------------
cat << 'VM_INSTRUCTIONS'
================================================================================
STEP 1: CREATE VM IN ORACLE CLOUD CONSOLE (Manual Steps)
================================================================================

1. Log in to Oracle Cloud Console: https://cloud.oracle.com/

2. Navigate to: Compute → Instances → Create Instance

3. Configure Instance:
   - Name: ai-employee-cloud-vm
   - Compartment: Select your compartment
   - Availability Domain: Any (prefer AD-1 for lowest latency)
   
4. Image and Shape:
   - Image: Ubuntu 24.04 LTS (Oracle-provided)
   - Shape: VM.Standard.A1.Flex (ARM Ampere)
   - OCPUs: 4 (maximum free tier)
   - Memory: 24 GB (maximum free tier)
   
5. Networking:
   - VCN: Create new or select existing
   - Subnet: Public subnet
   - Assign public IPv4 address: YES
   
6. SSH Keys:
   - Generate key pair OR upload your existing public key
   - Download private key securely
   
7. Boot Volume:
   - Size: 200 GB (maximum free tier)
   - Type: Balanced

8. Click "Create" and wait for instance to be RUNNING

9. Note the Public IP address (e.g., 129.146.xx.xx)

================================================================================
VM_INSTRUCTIONS

echo ""
read -p "Have you created the VM and noted the Public IP? (y/n): " confirmed
if [ "$confirmed" != "y" ]; then
    echo "Please create the VM first, then run this script again."
    exit 0
fi

read -p "Enter the Public IP address of your VM: " VM_IP
read -p "Enter the path to your SSH private key: " SSH_KEY_PATH

#-------------------------------------------------------------------------------
# SSH Connection Test
#-------------------------------------------------------------------------------
echo ""
echo "[1/8] Testing SSH connection..."
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no ubuntu@"$VM_IP" "echo 'SSH connection successful!'" || {
    echo "ERROR: SSH connection failed. Check your IP and key."
    exit 1
}

#-------------------------------------------------------------------------------
# Install Python 3.13 with uv
#-------------------------------------------------------------------------------
echo ""
echo "[2/8] Installing Python 3.13 and uv..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << 'PYTHON_INSTALL'
set -e

# Add deadsnakes PPA for Python 3.13
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update

# Install Python 3.13
sudo apt install -y python3.13 python3.13-venv python3.13-dev python3.13-distutils
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1

# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Verify installation
python3 --version
uv --version

PYTHON_INSTALL

#-------------------------------------------------------------------------------
# Install Node.js v24 LTS
#-------------------------------------------------------------------------------
echo ""
echo "[3/8] Installing Node.js v24 LTS..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << 'NODEJS_INSTALL'
set -e

# Install Node.js v24 using NodeSource
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs

# Verify installation
node --version
npm --version

NODEJS_INSTALL

#-------------------------------------------------------------------------------
# Install PM2 (Process Manager)
#-------------------------------------------------------------------------------
echo ""
echo "[4/8] Installing PM2..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << 'PM2_INSTALL'
set -e

# Install PM2 globally
sudo npm install -g pm2

# Setup PM2 to start on boot
pm2 startup
# Note: Run the output command if pm2 startup provides one

# Verify installation
pm2 --version

PM2_INSTALL

#-------------------------------------------------------------------------------
# Install Google Chrome (Headless for Playwright)
#-------------------------------------------------------------------------------
echo ""
echo "[5/8] Installing Google Chrome (headless)..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << 'CHROME_INSTALL'
set -e

# Download and install Google Chrome
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt.sources.list.d/google-chrome.list

sudo apt update
sudo apt install -y google-chrome-stable

# Verify Chrome installation
google-chrome --version

CHROME_INSTALL

#-------------------------------------------------------------------------------
# Install Git, nginx, certbot
#-------------------------------------------------------------------------------
echo ""
echo "[6/8] Installing Git, nginx, and certbot..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << 'TOOLS_INSTALL'
set -e

sudo apt install -y git nginx certbot python3-certbot-nginx

# Verify installations
git --version
nginx -v
certbot --version

TOOLS_INSTALL

#-------------------------------------------------------------------------------
# Install Docker and Docker Compose
#-------------------------------------------------------------------------------
echo ""
echo "[7/8] Installing Docker and Docker Compose..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << 'DOCKER_INSTALL'
set -e

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
rm get-docker.sh

# Add user to docker group
sudo usermod -aG docker ubuntu

# Install Docker Compose plugin
sudo apt install -y docker-compose-plugin

# Verify installations
docker --version
docker compose version

DOCKER_INSTALL

#-------------------------------------------------------------------------------
# Configure Firewall (ufw)
#-------------------------------------------------------------------------------
echo ""
echo "[8/8] Configuring firewall (ufw)..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << 'FIREWALL_CONFIG'
set -e

# Reset ufw (optional, be careful on remote machines)
# sudo ufw reset

# Set default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (critical - don't lock yourself out!)
sudo ufw allow 22/tcp comment "SSH"

# Allow HTTP and HTTPS (for nginx/Odoo)
sudo ufw allow 80/tcp comment "HTTP"
sudo ufw allow 443/tcp comment "HTTPS"

# Allow Odoo port (will be proxied through nginx)
sudo ufw allow 8069/tcp comment "Odoo"

# Enable firewall
sudo ufw --force enable

# Show status
sudo ufw status verbose

FIREWALL_CONFIG

#-------------------------------------------------------------------------------
# Create Project Directory Structure
#-------------------------------------------------------------------------------
echo ""
echo "Creating project directory structure on VM..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << 'DIR_STRUCTURE'
set -e

# Create main project directory
mkdir -p ~/ai_employee_vault
cd ~/ai_employee_vault

# Create folder structure
mkdir -p Inbox Needs_Action Needs_Approval Approved Done
mkdir -p Briefings Logs Updates In_Progress
mkdir -p platinum/odoo platinum/backups platinum/logs

# Create .gitkeep files
touch Inbox/.gitkeep Needs_Action/.gitkeep Needs_Approval/.gitkeep
touch Approved/.gitkeep Done/.gitkeep Briefings/.gitkeep
touch Logs/.gitkeep Updates/.gitkeep In_Progress/.gitkeep

# Set permissions
chmod -R 755 ~/ai_employee_vault

echo "Directory structure created:"
ls -la ~/ai_employee_vault/

DIR_STRUCTURE

#-------------------------------------------------------------------------------
# Summary
#-------------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "  PHASE 1A COMPLETE!"
echo "=============================================="
echo ""
echo "VM IP Address: $VM_IP"
echo ""
echo "Installed Components:"
echo "  ✓ Python 3.13 with uv"
echo "  ✓ Node.js v24 LTS"
echo "  ✓ PM2 (Process Manager)"
echo "  ✓ Google Chrome (headless)"
echo "  ✓ Git, nginx, certbot"
echo "  ✓ Docker + Docker Compose"
echo "  ✓ Firewall (ufw) configured"
echo ""
echo "Next Steps:"
echo "  1. Run Phase 1B: Odoo Community Deployment"
echo "  2. Copy your watcher scripts to the VM"
echo "  3. Configure PM2 for 24/7 watchers"
echo ""
echo "SSH into VM:"
echo "  ssh -i $SSH_KEY_PATH ubuntu@$VM_IP"
echo ""
