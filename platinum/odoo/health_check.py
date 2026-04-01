#!/usr/bin/env python3
"""
PLATINUM PHASE 1B: Odoo Health Monitoring Script
Purpose: Monitor Odoo container health and auto-restart if unresponsive
Target: Oracle Cloud Free Tier VM
Schedule: Runs every 60 seconds via PM2
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# Configuration
ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069")
HEALTH_ENDPOINT = f"{ODOO_URL}/web/health"
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))  # seconds
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "10"))  # seconds
LOG_PATH = os.getenv("LOG_PATH", "/home/ubuntu/ai_employee_vault/Logs/odoo_health.jsonl")
ODOO_CONTAINER = os.getenv("ODOO_CONTAINER", "odoo_community")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/odoo_health_monitor.log')
    ]
)
logger = logging.getLogger(__name__)


def log_health_status(status: str, details: dict):
    """Log health status to JSONL file for audit trail."""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "status": status,
        **details
    }
    
    # Ensure log directory exists
    log_path = Path(LOG_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Append to JSONL file
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")


def check_odoo_health() -> tuple[bool, int]:
    """
    Check Odoo health endpoint.
    Returns: (is_healthy, response_time_ms)
    """
    try:
        start_time = time.time()
        request = Request(HEALTH_ENDPOINT, method='GET')
        request.add_header('User-Agent', 'Odoo-Health-Monitor/1.0')
        
        with urlopen(request, timeout=30) as response:
            response_time_ms = int((time.time() - start_time) * 1000)
            
            if response.status == 200:
                return True, response_time_ms
            else:
                return False, response_time_ms
                
    except HTTPError as e:
        logger.warning(f"HTTP Error: {e.code}")
        return False, 0
    except URLError as e:
        logger.warning(f"URL Error: {e.reason}")
        return False, 0
    except Exception as e:
        logger.warning(f"Health check failed: {e}")
        return False, 0


def restart_odoo_container():
    """Restart Odoo Docker container."""
    logger.warning("Attempting to restart Odoo container...")
    
    try:
        # Stop container
        subprocess.run(
            ["docker", "stop", ODOO_CONTAINER],
            capture_output=True,
            text=True,
            timeout=60
        )
        logger.info("Odoo container stopped")
        
        time.sleep(5)  # Wait for container to fully stop
        
        # Start container
        subprocess.run(
            ["docker", "start", ODOO_CONTAINER],
            capture_output=True,
            text=True,
            timeout=60
        )
        logger.info("Odoo container started")
        
        log_health_status("restart_success", {
            "action": "container_restart",
            "container": ODOO_CONTAINER
        })
        
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("Docker command timed out")
        log_health_status("restart_failed", {
            "action": "container_restart",
            "error": "timeout"
        })
        return False
    except Exception as e:
        logger.error(f"Failed to restart container: {e}")
        log_health_status("restart_failed", {
            "action": "container_restart",
            "error": str(e)
        })
        return False


def check_docker_container_status() -> bool:
    """Check if Docker container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", ODOO_CONTAINER],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip().lower() == "true"
    except Exception as e:
        logger.error(f"Failed to check container status: {e}")
        return False


def monitor_loop():
    """Main monitoring loop."""
    logger.info(f"Starting Odoo Health Monitor")
    logger.info(f"Monitoring URL: {HEALTH_ENDPOINT}")
    logger.info(f"Check interval: {CHECK_INTERVAL}s")
    logger.info(f"Log path: {LOG_PATH}")
    
    consecutive_failures = 0
    last_restart_time = 0
    restart_cooldown = 300  # 5 minutes cooldown between restarts
    
    while True:
        try:
            # Check health
            is_healthy, response_time = check_odoo_health()
            
            if is_healthy:
                consecutive_failures = 0
                logger.info(f"✓ Odoo is healthy (response: {response_time}ms)")
                
                log_health_status("healthy", {
                    "response_time_ms": response_time,
                    "endpoint": HEALTH_ENDPOINT
                })
            else:
                consecutive_failures += 1
                logger.warning(
                    f"⚠ Odoo health check failed ({consecutive_failures}/{MAX_RETRIES})"
                )
                
                # Check if container is still running
                container_running = check_docker_container_status()
                
                log_health_status("unhealthy", {
                    "consecutive_failures": consecutive_failures,
                    "container_running": container_running,
                    "endpoint": HEALTH_ENDPOINT
                })
                
                # Attempt restart if max retries reached
                if consecutive_failures >= MAX_RETRIES:
                    current_time = time.time()
                    
                    if current_time - last_restart_time > restart_cooldown:
                        logger.error(
                            f"Max retries reached. Restarting Odoo container..."
                        )
                        
                        if restart_odoo_container():
                            consecutive_failures = 0
                            last_restart_time = current_time
                        else:
                            logger.error("Restart failed. Will retry on next cycle.")
                    else:
                        logger.warning(
                            f"Restart cooldown active. "
                            f"Waiting {restart_cooldown}s between restarts."
                        )
                        
        except KeyboardInterrupt:
            logger.info("Monitor interrupted by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error in monitor loop: {e}")
            log_health_status("error", {
                "error": str(e),
                "type": type(e).__name__
            })
        
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    monitor_loop()
