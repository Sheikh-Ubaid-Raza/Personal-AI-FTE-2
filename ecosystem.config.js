// AI Employee — PM2 Process Manager Configuration
// Usage: pm2 start ecosystem.config.js
//        pm2 stop all
//        pm2 logs

module.exports = {
  apps: [
    // ── File Watcher (Eyes — monitors Inbox/) ────────────────────────
    {
      name: "watcher",
      script: "watcher.py",
      interpreter: "/usr/bin/python3",
      cwd: __dirname,

      // Restart policy
      autorestart: true,
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 3000, // 3s between restarts

      // Logging
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "Logs/pm2-watcher-error.log",
      out_file: "Logs/pm2-watcher-out.log",
      merge_logs: true,

      // Environment
      env: {
        PYTHONUNBUFFERED: "1", // flush prints immediately to logs
      },
    },

    // ── Gmail Watcher (Ears — polls Gmail API) ───────────────────────
    {
      name: "gmail-watcher",
      script: "gmail_watcher.py",
      interpreter: "/usr/bin/python3",
      cwd: __dirname,

      autorestart: true,
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 5000, // 5s — be gentle with API rate limits

      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "Logs/pm2-gmail-watcher-error.log",
      out_file: "Logs/pm2-gmail-watcher-out.log",
      merge_logs: true,

      env: {
        PYTHONUNBUFFERED: "1",
      },
    },

    // ── Orchestrator (Brain — triage, plans, HITL, skills) ───────────
    {
      name: "orchestrator",
      script: "orchestrator.py",
      interpreter: "/usr/bin/python3",
      cwd: __dirname,

      autorestart: true,
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 3000,

      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "Logs/pm2-orchestrator-error.log",
      out_file: "Logs/pm2-orchestrator-out.log",
      merge_logs: true,

      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
