/**
 * PLATINUM PHASE 1A: PM2 Ecosystem Configuration
 * Purpose: Run watchers, orchestrator, and dashboard as 24/7 daemons with auto-restart
 * Target: Oracle Cloud Free Tier VM
 */

module.exports = {
  apps: [
    {
      /**
       * Heagent Dashboard (Next.js)
       * Modern React UI for monitoring and approvals
       * Runs on port 3000, proxied by nginx on port 443
       */
      name: 'heagent-dashboard',
      script: 'npm',
      args: 'start',
      cwd: '/home/ubuntu/ai_employee_vault/heagent-dashboard',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      env: {
        NODE_ENV: 'production',
        PORT: '3000',
        VAULT_PATH: '/home/ubuntu/ai_employee_vault',
        ODOO_URL: 'http://localhost:8069',
        ODOO_DB: 'postgres',
        ODOO_USER: 'odoo',
        ODOO_PASSWORD: process.env.ODOO_DB_PASSWORD,
        PM2_AVAILABLE: 'true',
      },
      error_file: '/home/ubuntu/ai_employee_vault/platinum/logs/dashboard-error.log',
      out_file: '/home/ubuntu/ai_employee_vault/platinum/logs/dashboard-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,
      restart_delay: 5000,
      max_restarts: 10,
      min_uptime: '30s',
    },
    {
      /**
       * Gmail Watcher
       * Monitors Gmail API for new unread/important emails
       * Creates .md files in /Needs_Action/ for Claude to process
       */
      name: 'gmail-watcher',
      script: './gmail_watcher.py',
      interpreter: 'python3',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        PYTHONUNBUFFERED: '1',
        CHECK_INTERVAL: '120', // Check every 120 seconds
        VAULT_PATH: '/home/ubuntu/ai_employee_vault',
        LOG_LEVEL: 'INFO',
      },
      error_file: '/home/ubuntu/ai_employee_vault/platinum/logs/gmail-watcher-error.log',
      out_file: '/home/ubuntu/ai_employee_vault/platinum/logs/gmail-watcher-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,
      restart_delay: 5000, // 5 seconds before restart
      max_restarts: 10,
      min_uptime: '30s', // Consider crash if fails before 30s
    },
    {
      /**
       * Filesystem Watcher
       * Monitors /Inbox/ folder for dropped files
       * Uses watchdog for real-time file system events
       */
      name: 'filesystem-watcher',
      script: './watcher.py',
      interpreter: 'python3',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '300M',
      env: {
        PYTHONUNBUFFERED: '1',
        VAULT_PATH: '/home/ubuntu/ai_employee_vault',
        INBOX_PATH: '/home/ubuntu/ai_employee_vault/Inbox',
        LOG_LEVEL: 'INFO',
      },
      error_file: '/home/ubuntu/ai_employee_vault/platinum/logs/filesystem-watcher-error.log',
      out_file: '/home/ubuntu/ai_employee_vault/platinum/logs/filesystem-watcher-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,
      restart_delay: 5000,
      max_restarts: 10,
      min_uptime: '30s',
    },
    {
      /**
       * Orchestrator (Cloud Instance)
       * Scans /Needs_Action/ every 5 seconds
       * Generates plans, triages tasks, manages approvals
       * DRAFT-ONLY MODE: Cannot send emails or publish posts
       */
      name: 'orchestrator-cloud',
      script: './orchestrator.py',
      interpreter: 'python3',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      env: {
        PYTHONUNBUFFERED: '1',
        VAULT_PATH: '/home/ubuntu/ai_employee_vault',
        AGENT_TYPE: 'cloud', // 'cloud' or 'local' - determines capabilities
        DRAFT_ONLY: 'true', // Cloud agent cannot send/publish
        SCAN_INTERVAL: '5', // Check every 5 seconds
        LOG_LEVEL: 'INFO',
        MAX_ITERATIONS: '10', // Ralph Wiggum loop max iterations
      },
      error_file: '/home/ubuntu/ai_employee_vault/platinum/logs/orchestrator-cloud-error.log',
      out_file: '/home/ubuntu/ai_employee_vault/platinum/logs/orchestrator-cloud-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,
      restart_delay: 5000,
      max_restarts: 10,
      min_uptime: '30s',
    },
    {
      /**
       * Sync Manager (Phase 2)
       * Git-based vault sync between Cloud and Local
       * Auto-commits and pushes every 5 minutes
       * NOTE: Uncomment when implementing Phase 2
       */
      // {
      //   name: 'sync-manager',
      //   script: './platinum/sync_manager.py',
      //   interpreter: 'python3',
      //   instances: 1,
      //   autorestart: true,
      //   watch: false,
      //   max_memory_restart: '200M',
      //   env: {
      //     PYTHONUNBUFFERED: '1',
      //     VAULT_PATH: '/home/ubuntu/ai_employee_vault',
      //     SYNC_INTERVAL: '300', // Sync every 300 seconds (5 minutes)
      //     GIT_REMOTE: 'origin',
      //     GIT_BRANCH: 'main',
      //     LOG_LEVEL: 'INFO',
      //   },
      //   error_file: '/home/ubuntu/ai_employee_vault/platinum/logs/sync-manager-error.log',
      //   out_file: '/home/ubuntu/ai_employee_vault/platinum/logs/sync-manager-out.log',
      //   log_date_format: 'YYYY-MM-DD HH:mm:ss',
      //   merge_logs: true,
      //   restart_delay: 5000,
      //   max_restarts: 10,
      //   min_uptime: '30s',
      // },
    },
    {
      /**
       * Odoo Health Monitor (Phase 1B)
       * Monitors Odoo container health
       * Auto-restarts Odoo if unresponsive
       * NOTE: Uncomment when implementing Phase 1B
       */
      // {
      //   name: 'odoo-health-monitor',
      //   script: './platinum/odoo/health_check.py',
      //   interpreter: 'python3',
      //   instances: 1,
      //   autorestart: true,
      //   watch: false,
      //   max_memory_restart: '100M',
      //   env: {
      //     PYTHONUNBUFFERED: '1',
      //     ODOO_URL: 'http://localhost:8069',
      //     CHECK_INTERVAL: '60', // Check every 60 seconds
      //     LOG_PATH: '/home/ubuntu/ai_employee_vault/Logs/odoo_health.jsonl',
      //     LOG_LEVEL: 'INFO',
      //   },
      //   error_file: '/home/ubuntu/ai_employee_vault/platinum/logs/odoo-health-error.log',
      //   out_file: '/home/ubuntu/ai_employee_vault/platinum/logs/odoo-health-out.log',
      //   log_date_format: 'YYYY-MM-DD HH:mm:ss',
      //   merge_logs: true,
      //   restart_delay: 5000,
      //   max_restarts: 10,
      //   min_uptime: '30s',
      // },
    },
  ],
};
