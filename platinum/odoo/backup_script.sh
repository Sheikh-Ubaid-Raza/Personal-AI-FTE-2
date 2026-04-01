#!/bin/bash
#===============================================================================
# PLATINUM PHASE 1B: Odoo Backup Script
# Purpose: Daily backup of PostgreSQL database and Odoo filestore
# Target: Oracle Cloud Free Tier VM
# Schedule: Daily at 2:00 AM (configured in docker-compose.yml)
#===============================================================================

set -e

# Configuration
BACKUP_DIR="/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATE_ONLY=$(date +%Y%m%d)

# Odoo/Postgres configuration
PG_USER="odoo"
PG_DB="postgres"
PG_PASSWORD="${PGPASSWORD:-ChangeMe123!}"

# Log file
LOG_FILE="/backups/backup_${DATE_ONLY}.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

#-------------------------------------------------------------------------------
# Main Backup Function
#-------------------------------------------------------------------------------
perform_backup() {
    log "${GREEN}Starting Odoo backup process...${NC}"
    
    # Create backup directory for today
    TODAY_BACKUP_DIR="${BACKUP_DIR}/${DATE_ONLY}"
    mkdir -p "$TODAY_BACKUP_DIR"
    
    #---------------------------------------------------------------------------
    # Step 1: Backup PostgreSQL Database
    #---------------------------------------------------------------------------
    log "Backing up PostgreSQL database..."
    
    DB_DUMP_FILE="${TODAY_BACKUP_DIR}/odoo_db_${TIMESTAMP}.sql.gz"
    
    PGPASSWORD="$PG_PASSWORD" pg_dump -h db -U "$PG_USER" -d "$PG_DB" | gzip > "$DB_DUMP_FILE"
    
    if [ -f "$DB_DUMP_FILE" ] && [ -s "$DB_DUMP_FILE" ]; then
        DB_SIZE=$(du -h "$DB_DUMP_FILE" | cut -f1)
        log "${GREEN}✓ Database backup complete: ${DB_SIZE}${NC}"
    else
        log "${RED}✗ Database backup failed!${NC}"
        exit 1
    fi
    
    #---------------------------------------------------------------------------
    # Step 2: Backup Odoo Filestore
    #---------------------------------------------------------------------------
    log "Backing up Odoo filestore..."
    
    FILESTORE_DIR="/var/lib/odoo/filestore"
    FILESTORE_BACKUP="${TODAY_BACKUP_DIR}/odoo_filestore_${TIMESTAMP}.tar.gz"
    
    if [ -d "$FILESTORE_DIR" ]; then
        tar -czf "$FILESTORE_BACKUP" -C "$(dirname $FILESTORE_DIR)" "$(basename $FILESTORE_DIR)"
        
        if [ -f "$FILESTORE_BACKUP" ] && [ -s "$FILESTORE_BACKUP" ]; then
            FILESTORE_SIZE=$(du -h "$FILESTORE_BACKUP" | cut -f1)
            log "${GREEN}✓ Filestore backup complete: ${FILESTORE_SIZE}${NC}"
        else
            log "${RED}✗ Filestore backup failed!${NC}"
            exit 1
        fi
    else
        log "${YELLOW}⚠ Filestore directory not found, skipping...${NC}"
    fi
    
    #---------------------------------------------------------------------------
    # Step 3: Create Backup Manifest
    #---------------------------------------------------------------------------
    log "Creating backup manifest..."
    
    cat > "${TODAY_BACKUP_DIR}/manifest_${TIMESTAMP}.json" << EOF
{
    "backup_date": "$(date -Iseconds)",
    "timestamp": "${TIMESTAMP}",
    "database": "${PG_DB}",
    "database_file": "$(basename $DB_DUMP_FILE)",
    "database_size": "$(du -b $DB_DUMP_FILE | cut -f1)",
    "filestore_file": "$(basename $FILESTORE_BACKUP)",
    "filestore_size": "$(du -b $FILESTORE_BACKUP | cut -f1)",
    "retention_days": ${RETENTION_DAYS},
    "backup_type": "full"
}
EOF
    
    log "${GREEN}✓ Backup manifest created${NC}"
    
    #---------------------------------------------------------------------------
    # Step 4: Cleanup Old Backups
    #---------------------------------------------------------------------------
    log "Cleaning up backups older than ${RETENTION_DAYS} days..."
    
    find "$BACKUP_DIR" -type d -name "20*" -mtime +${RETENTION_DAYS} -exec rm -rf {} \; 2>/dev/null || true
    find "$BACKUP_DIR" -type f -name "*.log" -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true
    
    log "${GREEN}✓ Old backups cleaned up${NC}"
    
    #---------------------------------------------------------------------------
    # Step 5: Summary
    #---------------------------------------------------------------------------
    log ""
    log "${GREEN}=============================================${NC}"
    log "${GREEN}  BACKUP COMPLETE!${NC}"
    log "${GREEN}=============================================${NC}"
    log ""
    log "Backup Location: ${TODAY_BACKUP_DIR}"
    log "Database: ${DB_SIZE}"
    log "Filestore: ${FILESTORE_SIZE:-N/A}"
    log "Retention: ${RETENTION_DAYS} days"
    log ""
}

#-------------------------------------------------------------------------------
# Error Handler
#-------------------------------------------------------------------------------
error_handler() {
    log "${RED}=============================================${NC}"
    log "${RED}  BACKUP FAILED!${NC}"
    log "${RED}=============================================${NC}"
    log "Error on line $1"
    
    # Send alert (optional - integrate with your notification system)
    # For now, just log the error
    exit 1
}

trap 'error_handler $LINENO' ERR

#-------------------------------------------------------------------------------
# Main Execution
#-------------------------------------------------------------------------------
perform_backup
