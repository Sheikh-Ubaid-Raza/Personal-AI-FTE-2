#!/bin/bash
#===============================================================================
# PLATINUM PHASE 1: Final Verification Runner
# Purpose: Run comprehensive health check on Oracle Cloud VM
# Usage: ./run_phase1_verification.sh [VM_IP] [SSH_KEY]
#===============================================================================

set -e

echo ""
echo "=============================================="
echo "  PLATINUM PHASE 1: FINAL VERIFICATION"
echo "=============================================="
echo ""

# Configuration
VAULT_PATH="${VAULT_PATH:-$HOME/ai_employee_vault}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if running on VM or locally
if [ -n "$1" ]; then
    # Running locally - SSH to VM
    VM_IP="$1"
    SSH_KEY="$2"
    
    if [ -z "$SSH_KEY" ]; then
        echo "ERROR: SSH key required when running remotely"
        echo "Usage: $0 <VM_IP> <SSH_KEY>"
        exit 1
    fi
    
    echo "Running verification on VM: $VM_IP"
    echo ""
    
    # Copy verification script to VM
    echo "[1/3] Copying verification script to VM..."
    scp -i "$SSH_KEY" \
        "$SCRIPT_DIR/phase1_verification.py" \
        ubuntu@"$VM_IP":~/phase1_verification.py
    
    # Set environment variables and run on VM
    echo "[2/3] Running verification on VM..."
    echo ""
    
    ssh -i "$SSH_KEY" ubuntu@"$VM_IP" << SSHCMDS
set -e

# Set environment variables
export VAULT_PATH=/home/ubuntu/ai_employee_vault
export ODOO_URL=http://localhost:8069
export ODOO_DB=postgres
export ODOO_USER=odoo
export ODOO_PASSWORD=\$(grep ODOO_DB_PASSWORD /home/ubuntu/ai_employee_vault/platinum/odoo/.env | cut -d'=' -f2)
export DASHBOARD_URL=http://localhost:3000
export VM_IP=$(hostname -I | awk '{print \$1}')

# Run verification
cd /home/ubuntu/ai_employee_vault
python3 phase1_verification.py

# Clean up
rm phase1_verification.py

SSHCMDS
    
    echo ""
    echo "[3/3] Verification complete!"
    
else
    # Running directly on VM
    echo "Running verification locally on VM..."
    echo ""
    
    # Load environment variables
    if [ -f "$VAULT_PATH/platinum/odoo/.env" ]; then
        export ODOO_DB_PASSWORD=$(grep ODOO_DB_PASSWORD "$VAULT_PATH/platinum/odoo/.env" | cut -d'=' -f2)
    fi
    
    export VAULT_PATH="$VAULT_PATH"
    export ODOO_URL="http://localhost:8069"
    export ODOO_DB="postgres"
    export ODOO_USER="odoo"
    export ODOO_PASSWORD="${ODOO_DB_PASSWORD:-}"
    export DASHBOARD_URL="http://localhost:3000"
    export VM_IP=$(hostname -I | awk '{print $1}')
    
    # Run verification
    cd "$VAULT_PATH"
    python3 "$SCRIPT_DIR/phase1_verification.py"
fi

echo ""
echo "=============================================="
echo "  VERIFICATION COMPLETE"
echo "=============================================="
echo ""
