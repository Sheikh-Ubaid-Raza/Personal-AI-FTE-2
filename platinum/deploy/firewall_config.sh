#!/bin/bash
#===============================================================================
# PLATINUM PHASE 1A: Firewall Configuration Script
# Purpose: Configure ufw firewall for Oracle Cloud VM
# Target: Ubuntu 24.04 LTS on Oracle Cloud Free Tier
#===============================================================================

set -e

echo "=============================================="
echo "  PLATINUM PHASE 1A: Firewall Configuration"
echo "=============================================="
echo ""

#-------------------------------------------------------------------------------
# IMPORTANT: Oracle Cloud Network Security Groups (NSG)
#-------------------------------------------------------------------------------
cat << 'NSG_INSTRUCTIONS'
================================================================================
STEP 0: Configure Oracle Cloud Network Security Groups (Manual)
================================================================================

BEFORE running this script, you MUST configure Oracle Cloud NSGs:

1. Go to Oracle Cloud Console → Networking → Virtual Cloud Networks
2. Click on your VCN
3. Click on Security Lists → Default Security List
4. Add the following INGRESS RULES:

   | Source      | Protocol | Port Range | Purpose           |
   |-------------|----------|------------|-------------------|
   | 0.0.0.0/0   | TCP      | 22         | SSH               |
   | 0.0.0.0/0   | TCP      | 80         | HTTP (nginx)      |
   | 0.0.0.0/0   | TCP      | 443        | HTTPS (nginx)     |
   | 0.0.0.0/0   | TCP      | 8069       | Odoo (optional*)  |

   *Note: Odoo should be accessed through nginx (port 443), not directly.
   You can skip port 8069 if you only access Odoo via nginx proxy.

5. Click "Add Ingress Rules"

================================================================================
NSG_INSTRUCTIONS

echo ""
read -p "Have you configured the Oracle Cloud NSG ingress rules? (y/n): " confirmed
if [ "$confirmed" != "y" ]; then
    echo "Please configure NSG rules first, then run this script."
    exit 0
fi

#-------------------------------------------------------------------------------
# Read VM IP for validation
#-------------------------------------------------------------------------------
read -p "Enter your VM's public IP address: " VM_IP

#-------------------------------------------------------------------------------
# Configure ufw on VM
#-------------------------------------------------------------------------------
echo ""
echo "Configuring ufw firewall on VM..."
echo ""

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << 'FIREWALL_SCRIPT'
set -e

echo "Current ufw status:"
sudo ufw status verbose || true

echo ""
echo "Resetting ufw (if enabled)..."
sudo ufw --force reset || true

echo ""
echo "Setting default policies..."
sudo ufw default deny incoming
sudo ufw default allow outgoing

echo ""
echo "Adding firewall rules..."

# Allow SSH (critical!)
sudo ufw allow 22/tcp comment "SSH - Remote access"
echo "  ✓ Added SSH (port 22)"

# Allow HTTP (for Let's Encrypt validation and nginx)
sudo ufw allow 80/tcp comment "HTTP - Web traffic"
echo "  ✓ Added HTTP (port 80)"

# Allow HTTPS (for secure web traffic)
sudo ufw allow 443/tcp comment "HTTPS - Secure web traffic"
echo "  ✓ Added HTTPS (port 443)"

# Allow Odoo port (optional - only if direct access needed)
# Note: Production should use nginx proxy on port 443
sudo ufw allow 8069/tcp comment "Odoo - Direct access (optional)"
echo "  ✓ Added Odoo (port 8069)"

echo ""
echo "Enabling firewall..."
sudo ufw --force enable

echo ""
echo "Final firewall status:"
sudo ufw status verbose

echo ""
echo "Testing SSH rule (should still be connected)..."
# If we're still connected, SSH rule is working

FIREWALL_SCRIPT

#-------------------------------------------------------------------------------
# Verification
#-------------------------------------------------------------------------------
echo ""
echo "Verifying firewall configuration..."

ssh -i "$SSH_KEY_PATH" ubuntu@"$VM_IP" << 'VERIFY'
echo ""
echo "Port availability check:"
echo "------------------------"

# Check if ports are listening
sudo ss -tlnp | grep -E ':(22|80|443|8069)\s' || echo "No ports listening yet (expected if services not started)"

VERIFY

#-------------------------------------------------------------------------------
# Summary
#-------------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "  FIREWALL CONFIGURATION COMPLETE!"
echo "=============================================="
echo ""
echo "Configured Rules:"
echo "  ✓ SSH (22/tcp) - Remote access"
echo "  ✓ HTTP (80/tcp) - Web traffic / Let's Encrypt"
echo "  ✓ HTTPS (443/tcp) - Secure web traffic"
echo "  ✓ Odoo (8069/tcp) - Direct Odoo access (optional)"
echo ""
echo "Default Policies:"
echo "  - Incoming: DENY (unless explicitly allowed)"
echo "  - Outgoing: ALLOW"
echo ""
echo "IMPORTANT NOTES:"
echo "  1. Oracle Cloud NSG rules must also be configured (see above)"
echo "  2. Odoo should be accessed via nginx (port 443), not directly"
echo "  3. Never disable SSH rule while connected remotely!"
echo ""
echo "To check firewall status anytime:"
echo "  ssh -i <key> ubuntu@${VM_IP} 'sudo ufw status verbose'"
echo ""
