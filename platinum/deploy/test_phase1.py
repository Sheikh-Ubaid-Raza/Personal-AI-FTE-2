#!/usr/bin/env python3
"""
PLATINUM PHASE 1: Deployment Verification Script
Purpose: Test all Phase 1 components after deployment
Target: Oracle Cloud Free Tier VM
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ANSI Colors
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color

# Configuration
VAULT_PATH = Path(os.getenv("VAULT_PATH", Path.home() / "ai_employee_vault"))
ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069")
NGINX_HEALTH = "http://localhost/nginx-health"


def log_section(title: str):
    """Print section header."""
    print(f"\n{BLUE}{'=' * 60}{NC}")
    print(f"{BLUE}{title:^60}{NC}")
    print(f"{BLUE}{'=' * 60}{NC}\n")


def log_test(name: str, passed: bool, details: str = ""):
    """Print test result."""
    status = f"{GREEN}✓ PASS{NC}" if passed else f"{RED}✗ FAIL{NC}"
    print(f"{status} - {name}")
    if details:
        print(f"       {details}")


def test_directory_structure():
    """Test: Directory structure exists."""
    log_section("Test 1: Directory Structure")
    
    required_dirs = [
        "Inbox",
        "Needs_Action",
        "Needs_Approval",
        "Approved",
        "Done",
        "Briefings",
        "Logs",
        "Updates",
        "In_Progress",
        "platinum/odoo",
        "platinum/logs",
        "platinum/backups",
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        full_path = VAULT_PATH / dir_path
        exists = full_path.exists()
        log_test(f"Directory: {dir_path}", exists)
        if not exists:
            all_exist = False
    
    return all_exist


def test_python_environment():
    """Test: Python 3.13 and dependencies installed."""
    log_section("Test 2: Python Environment")
    
    # Check Python version
    try:
        result = subprocess.run(
            ["python3", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        version = result.stdout.strip()
        passed = "3.13" in version
        log_test("Python 3.13 installed", passed, version)
    except Exception as e:
        log_test("Python 3.13 installed", False, str(e))
        return False
    
    # Check required packages
    required_packages = ["watchdog", "google-api-python-client", "playwright"]
    all_installed = True
    
    for package in required_packages:
        try:
            subprocess.run(
                ["python3", "-c", f"import {package}"],
                capture_output=True,
                timeout=10
            )
            log_test(f"Package: {package}", True)
        except Exception:
            log_test(f"Package: {package}", False)
            all_installed = False
    
    return all_installed


def test_pm2_watchers():
    """Test: PM2 watchers running."""
    log_section("Test 3: PM2 Watchers")
    
    try:
        result = subprocess.run(
            ["pm2", "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        output = result.stdout
        
        # Check for required processes
        required_processes = [
            "gmail-watcher",
            "filesystem-watcher",
            "orchestrator-cloud",
        ]
        
        all_running = True
        for process in required_processes:
            is_running = process in output and "online" in output
            log_test(f"PM2 Process: {process}", is_running)
            if not is_running:
                all_running = False
        
        return all_running
        
    except Exception as e:
        log_test("PM2 status check", False, str(e))
        return False


def test_docker_containers():
    """Test: Docker containers running."""
    log_section("Test 4: Docker Containers")
    
    try:
        result = subprocess.run(
            ["docker", "compose", "ps"],
            cwd=VAULT_PATH / "platinum" / "odoo",
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = result.stdout
        
        # Check for required containers
        required_containers = [
            "odoo_postgres",
            "odoo_community",
            "odoo_nginx",
            "odoo_certbot",
        ]
        
        all_running = True
        for container in required_containers:
            is_running = container in output and "running" in output.lower()
            log_test(f"Container: {container}", is_running)
            if not is_running:
                all_running = False
        
        return all_running
        
    except Exception as e:
        log_test("Docker status check", False, str(e))
        return False


def test_odoo_health():
    """Test: Odoo health endpoint."""
    log_section("Test 5: Odoo Health")
    
    try:
        request = Request(f"{ODOO_URL}/web/health")
        request.add_header('User-Agent', 'Odoo-Health-Check/1.0')
        
        start_time = time.time()
        with urlopen(request, timeout=30) as response:
            response_time = int((time.time() - start_time) * 1000)
            
            if response.status == 200:
                log_test("Odoo health endpoint", True, f"Response: {response_time}ms")
                return True
            else:
                log_test("Odoo health endpoint", False, f"Status: {response.status}")
                return False
                
    except HTTPError as e:
        log_test("Odoo health endpoint", False, f"HTTP Error: {e.code}")
        return False
    except URLError as e:
        log_test("Odoo health endpoint", False, f"URL Error: {e.reason}")
        return False
    except Exception as e:
        log_test("Odoo health endpoint", False, str(e))
        return False


def test_nginx_health():
    """Test: nginx health endpoint."""
    log_section("Test 6: nginx Health")
    
    try:
        request = Request(NGINX_HEALTH)
        request.add_header('User-Agent', 'Nginx-Health-Check/1.0')
        
        start_time = time.time()
        with urlopen(request, timeout=10) as response:
            response_time = int((time.time() - start_time) * 1000)
            
            if response.status == 200:
                log_test("nginx health endpoint", True, f"Response: {response_time}ms")
                return True
            else:
                log_test("nginx health endpoint", False, f"Status: {response.status}")
                return False
                
    except Exception as e:
        log_test("nginx health endpoint", False, str(e))
        return False


def test_backup_configuration():
    """Test: Backup script and schedule."""
    log_section("Test 7: Backup Configuration")
    
    backup_script = VAULT_PATH / "platinum" / "odoo" / "backup_script.sh"
    backup_dir = VAULT_PATH / "platinum" / "backups"
    
    # Check backup script exists
    script_exists = backup_script.exists()
    log_test("Backup script exists", script_exists)
    
    # Check backup directory exists
    dir_exists = backup_dir.exists()
    log_test("Backup directory exists", dir_exists)
    
    # Check backup script is executable
    if script_exists:
        is_executable = os.access(backup_script, os.X_OK)
        log_test("Backup script executable", is_executable)
        return script_exists and dir_exists and is_executable
    
    return False


def test_firewall_configuration():
    """Test: Firewall rules configured."""
    log_section("Test 8: Firewall Configuration")
    
    try:
        result = subprocess.run(
            ["sudo", "ufw", "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        output = result.stdout
        
        # Check required rules
        required_rules = {
            "22/tcp": "SSH",
            "80/tcp": "HTTP",
            "443/tcp": "HTTPS",
        }
        
        all_configured = True
        for rule, description in required_rules.items():
            is_configured = rule in output and "ALLOW" in output
            log_test(f"Firewall rule: {description} ({rule})", is_configured)
            if not is_configured:
                all_configured = False
        
        return all_configured
        
    except Exception as e:
        log_test("Firewall status check", False, str(e))
        return False


def test_cloud_agent_config():
    """Test: Cloud agent configuration (DRAFT_ONLY mode)."""
    log_section("Test 9: Cloud Agent Configuration")
    
    ecosystem_config = VAULT_PATH / "ecosystem.config.js"
    
    if not ecosystem_config.exists():
        log_test("PM2 ecosystem config exists", False)
        return False
    
    content = ecosystem_config.read_text()
    
    # Check for cloud agent settings
    checks = {
        "AGENT_TYPE": "cloud" in content,
        "DRAFT_ONLY": "true" in content,
        "orchestrator-cloud": "orchestrator-cloud" in content,
    }
    
    all_configured = True
    for setting, passed in checks.items():
        log_test(f"Config setting: {setting}", passed)
        if not passed:
            all_configured = False
    
    return all_configured


def test_dashboard_deployment():
    """Test: Next.js Dashboard deployment."""
    log_section("Test 10: Dashboard Deployment")
    
    dashboard_dir = VAULT_PATH / "heagent-dashboard"
    
    # Check dashboard directory exists
    dir_exists = dashboard_dir.exists()
    log_test("Dashboard directory exists", dir_exists)
    if not dir_exists:
        return False
    
    # Check package.json exists
    package_json = dashboard_dir / "package.json"
    package_exists = package_json.exists()
    log_test("package.json exists", package_exists)
    
    # Check .env.local exists
    env_local = dashboard_dir / ".env.local"
    env_exists = env_local.exists()
    log_test(".env.local exists", env_exists)
    
    # Check if dashboard is running (port 3000)
    try:
        request = Request("http://localhost:3000/api/health")
        request.add_header('User-Agent', 'Dashboard-Health-Check/1.0')
        
        with urlopen(request, timeout=10) as response:
            if response.status == 200:
                log_test("Dashboard API health", True, "Responding on port 3000")
                api_healthy = True
            else:
                log_test("Dashboard API health", False, f"Status: {response.status}")
                api_healthy = False
    except Exception as e:
        log_test("Dashboard API health", False, str(e))
        api_healthy = False
    
    # Check PM2 process
    try:
        result = subprocess.run(
            ["pm2", "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        pm2_running = "heagent-dashboard" in result.stdout and "online" in result.stdout
        log_test("PM2 dashboard process", pm2_running)
    except Exception:
        pm2_running = False
    
    return package_exists and env_exists and api_healthy and pm2_running


def run_all_tests():
    """Run all Phase 1 deployment tests."""
    print(f"\n{GREEN}{'=' * 60}{NC}")
    print(f"{GREEN}{'PLATINUM PHASE 1: DEPLOYMENT VERIFICATION':^60}{NC}")
    print(f"{GREEN}{'=' * 60}{NC}")
    print(f"\nTimestamp: {datetime.utcnow().isoformat()}Z")
    print(f"Vault Path: {VAULT_PATH}")
    
    tests = [
        ("Directory Structure", test_directory_structure),
        ("Python Environment", test_python_environment),
        ("PM2 Watchers", test_pm2_watchers),
        ("Docker Containers", test_docker_containers),
        ("Odoo Health", test_odoo_health),
        ("nginx Health", test_nginx_health),
        ("Backup Configuration", test_backup_configuration),
        ("Firewall Configuration", test_firewall_configuration),
        ("Cloud Agent Config", test_cloud_agent_config),
        ("Dashboard Deployment", test_dashboard_deployment),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"{RED}ERROR running {name}: {e}{NC}")
            results.append((name, False))
    
    # Summary
    log_section("Test Summary")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for name, passed in results:
        status = f"{GREEN}✓{NC}" if passed else f"{RED}✗{NC}"
        print(f"{status} {name}")
    
    print(f"\n{'=' * 60}")
    print(f"Total: {passed_count}/{total_count} tests passed")
    print(f"{'=' * 60}\n")
    
    if passed_count == total_count:
        print(f"{GREEN}✓ ALL TESTS PASSED! Phase 1 deployment is ready.{NC}\n")
        return 0
    else:
        print(f"{YELLOW}⚠ Some tests failed. Review the output above.{NC}\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
