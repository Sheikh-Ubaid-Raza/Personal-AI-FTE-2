#!/bin/bash
# AI Employee — Cron Job Setup Script
# Adds scheduled tasks to WSL crontab for automated operations.
# 
# Usage: ./setup_cron.sh
# View cron: crontab -l
# Remove all: crontab -r (then re-run this script)

set -e

VAULT_PATH="/mnt/c/h-0/ai_employee_vault_bronze"
PYTHON="/usr/bin/python3"

echo "Setting up AI Employee cron jobs..."
echo ""

# Create cron entries
CRON_ENTRIES="# AI Employee — Automated Tasks
# ─────────────────────────────────────────────────────────────

# Monday Morning CEO Briefing at 8:00 AM
0 8 * * 1 cd $VAULT_PATH && $PYTHON .claude/skills/ceo-briefing/scripts/generate_briefing.py --days 7 >> $VAULT_PATH/Logs/cron_briefing.log 2>&1

# Daily task triage at 9:00 AM (Monday-Friday)
0 9 * * 1-5 cd $VAULT_PATH && $PYTHON .claude/skills/file-triage/scripts/triage.py >> $VAULT_PATH/Logs/cron_triage.log 2>&1

# Hourly health check (verify watchers are running)
0 * * * * cd $VAULT_PATH && pm2 list > /dev/null 2>&1 || echo \"PM2 not running\" >> $VAULT_PATH/Logs/cron_health.log
"

# Install cron entries
echo "$CRON_ENTRIES" | crontab -

echo "✓ Cron jobs installed successfully!"
echo ""
echo "Current crontab:"
echo "─────────────────────────────────────────────────────────"
crontab -l
echo "─────────────────────────────────────────────────────────"
echo ""
echo "To view logs: tail -f $VAULT_PATH/Logs/cron_*.log"
echo "To remove:    crontab -r"
