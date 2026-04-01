#!/usr/bin/env python3
"""
PLATINUM PHASE 1: Final Verification Script
Purpose: Comprehensive health check and connectivity audit before Phase 2
Target: Oracle Cloud Free Tier VM
Usage: Run locally or on the VM
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
CYAN = '\033[0;36m'
MAGENTA = '\033[0;35m'
NC = '\033[0m'  # No Color

# Configuration
VAULT_PATH = Path(os.getenv("VAULT_PATH", Path.home() / "ai_employee_vault"))
ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3000")

# Test Results Storage
test_results = {
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "vm_ip": os.getenv("VM_IP", "unknown"),
    "tests": [],
    "go_no_go": "PENDING"
}


def log_section(title: str, icon: str = "📋"):
    """Print section header with emoji."""
    print(f"\n{BLUE}{'=' * 70}{NC}")
    print(f"{BLUE}{icon}  {title:^64}{NC}")
    print(f"{BLUE}{'=' * 70}{NC}\n")


def log_test(name: str, passed: bool, details: str = "", critical: bool = False):
    """Print and store test result."""
    status_icon = "✅" if passed else "❌"
    status_color = GREEN if passed else RED
    status = f"{status_color}{status_icon} {status_color}PASS{NC}" if passed else f"{status_color}{status_icon} {status_color}FAIL{NC}"
    
    critical_marker = f" {RED}[CRITICAL]{NC}" if critical else ""
    
    print(f"{status}{critical_marker} - {name}")
    if details:
        print(f"       {CYAN}{details}{NC}")
    print()
    
    test_results["tests"].append({
        "name": name,
        "passed": passed,
        "details": details,
        "critical": critical
    })
    
    return passed


def run_command(cmd: list, timeout: int = 30, shell: bool = False) -> tuple:
    """Run shell command and return (success, stdout, stderr)."""
    try:
        if shell:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        else:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def test_vm_connectivity():
    """Test 1: VM Connectivity & SSH Access."""
    log_section("Test 1: VM Connectivity & SSH Access", "🔌")
    
    vm_ip = os.getenv("VM_IP", "")
    ssh_key = os.getenv("SSH_KEY", "")
    
    if not vm_ip:
        log_test("VM IP configured", False, "VM_IP environment variable not set", critical=True)
        return False
    
    log_test("VM IP configured", True, f"IP: {vm_ip}")
    
    # Test SSH connectivity
    if ssh_key:
        success, stdout, stderr = run_command(
            f"ssh -i {ssh_key} -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@{vm_ip} 'echo SSH_SUCCESS'",
            shell=True
        )
        if success and "SSH_SUCCESS" in stdout:
            log_test("SSH connection", True, "VM is accessible via SSH")
        else:
            log_test("SSH connection", False, f"Failed: {stderr[:100]}", critical=True)
            return False
    else:
        log_test("SSH connection", False, "SSH_KEY not provided - skipping SSH tests", critical=False)
    
    return True


def test_pm2_services():
    """Test 2: PM2 Service Status."""
    log_section("Test 2: PM2 Service Status", "⚙️")
    
    # Check if PM2 is installed
    success, stdout, stderr = run_command(["pm2", "--version"])
    if not success:
        log_test("PM2 installed", False, "PM2 is not installed on this system", critical=True)
        return False
    
    log_test("PM2 installed", True, stdout.strip())
    
    # Get PM2 status
    success, stdout, stderr = run_command(["pm2", "status", "--no-color"])
    if not success:
        log_test("PM2 status check", False, stderr[:100], critical=True)
        return False
    
    print(f"{CYAN}PM2 Process List:{NC}")
    print(stdout)
    
    # Check required processes
    required_processes = {
        "heagent-dashboard": "Dashboard (Port 3000)",
        "gmail-watcher": "Gmail Watcher",
        "filesystem-watcher": "Filesystem Watcher",
        "orchestrator-cloud": "Orchestrator (Cloud)",
    }
    
    all_running = True
    for process, description in required_processes.items():
        is_running = process in stdout and "online" in stdout.lower()
        log_test(f"PM2: {description}", is_running)
        if not is_running:
            all_running = False
    
    # Check PM2 memory usage
    success, stdout, stderr = run_command(["pm2", "jlist"])
    if success:
        try:
            processes = json.loads(stdout)
            total_memory = sum(p.get("monit", {}).get("memory", 0) for p in processes)
            total_memory_mb = total_memory / (1024 * 1024)
            log_test("PM2 memory usage", True, f"Total: {total_memory_mb:.1f} MB")
        except:
            log_test("PM2 memory usage", False, "Could not parse memory usage")
    
    return all_running


def test_docker_containers():
    """Test 3: Docker Container Status."""
    log_section("Test 3: Docker Container Status", "🐳")
    
    # Check if Docker is installed
    success, stdout, stderr = run_command(["docker", "--version"])
    if not success:
        log_test("Docker installed", False, "Docker is not installed", critical=True)
        return False
    
    log_test("Docker installed", True, stdout.strip())
    
    # Get Docker container status
    success, stdout, stderr = run_command(["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"])
    if not success:
        log_test("Docker status check", False, stderr[:100], critical=True)
        return False
    
    print(f"{CYAN}Docker Containers:{NC}")
    print(stdout)
    
    # Check required containers
    required_containers = {
        "odoo_community": "Odoo Community ERP",
        "odoo_postgres": "PostgreSQL Database",
        "odoo_nginx": "nginx Reverse Proxy",
        "odoo_certbot": "Let's Encrypt Certbot",
    }
    
    all_running = True
    for container, description in required_containers.items():
        is_running = container in stdout and "Up" in stdout
        log_test(f"Docker: {description}", is_running)
        if not is_running:
            all_running = False
    
    return all_running


def test_health_endpoints():
    """Test 4: Health Endpoint Connectivity."""
    log_section("Test 4: Health Endpoint Connectivity", "🏥")
    
    all_healthy = True
    
    # Test Odoo health endpoint
    try:
        request = Request(f"{ODOO_URL}/web/health")
        request.add_header('User-Agent', 'Phase1-Health-Check/1.0')
        
        start_time = time.time()
        with urlopen(request, timeout=30) as response:
            response_time = int((time.time() - start_time) * 1000)
            
            if response.status == 200:
                log_test("Odoo /web/health", True, f"200 OK ({response_time}ms)", critical=True)
            else:
                log_test("Odoo /web/health", False, f"Status: {response.status}", critical=True)
                all_healthy = False
    except Exception as e:
        log_test("Odoo /web/health", False, str(e)[:100], critical=True)
        all_healthy = False
    
    # Test Dashboard health endpoint
    try:
        request = Request(f"{DASHBOARD_URL}/api/health")
        request.add_header('User-Agent', 'Phase1-Health-Check/1.0')
        
        start_time = time.time()
        with urlopen(request, timeout=30) as response:
            response_time = int((time.time() - start_time) * 1000)
            
            if response.status == 200:
                log_test("Dashboard /api/health", True, f"200 OK ({response_time}ms)", critical=True)
            else:
                log_test("Dashboard /api/health", False, f"Status: {response.status}", critical=True)
                all_healthy = False
    except Exception as e:
        log_test("Dashboard /api/health", False, str(e)[:100], critical=True)
        all_healthy = False
    
    # Test nginx health endpoint
    try:
        request = Request("http://localhost/nginx-health")
        request.add_header('User-Agent', 'Phase1-Health-Check/1.0')
        
        start_time = time.time()
        with urlopen(request, timeout=10) as response:
            response_time = int((time.time() - start_time) * 1000)
            
            if response.status == 200:
                log_test("nginx /nginx-health", True, f"200 OK ({response_time}ms)")
            else:
                log_test("nginx /nginx-health", False, f"Status: {response.status}")
                all_healthy = False
    except Exception as e:
        log_test("nginx /nginx-health", False, str(e)[:100])
        all_healthy = False
    
    return all_healthy


def test_watcher_logs():
    """Test 5: Watcher Log Stability."""
    log_section("Test 5: Watcher Log Stability", "📜")
    
    log_path = VAULT_PATH / "platinum" / "logs"
    
    if not log_path.exists():
        log_test("Log directory exists", False, f"Path: {log_path}")
        return False
    
    log_test("Log directory exists", True, str(log_path))
    
    # Check Gmail watcher logs
    gmail_log = log_path / "gmail-watcher-out.log"
    if gmail_log.exists():
        success, stdout, stderr = run_command(["tail", "-10", str(gmail_log)])
        if success:
            print(f"{CYAN}Last 10 lines from gmail-watcher:{NC}")
            print(stdout)
            
            # Check for errors
            if "ERROR" in stdout or "Exception" in stdout:
                log_test("Gmail watcher logs", False, "Errors found in recent logs", critical=True)
                return False
            else:
                log_test("Gmail watcher logs", True, "No recent errors detected")
        else:
            log_test("Gmail watcher logs", False, "Could not read logs")
            return False
    else:
        log_test("Gmail watcher logs", False, "Log file not found")
        return False
    
    # Check orchestrator logs
    orchestrator_log = log_path / "orchestrator-cloud-out.log"
    if orchestrator_log.exists():
        success, stdout, stderr = run_command(["tail", "-10", str(orchestrator_log)])
        if success:
            print(f"{CYAN}Last 10 lines from orchestrator-cloud:{NC}")
            print(stdout)
            
            if "ERROR" in stdout or "Exception" in stdout:
                log_test("Orchestrator logs", False, "Errors found in recent logs")
                return False
            else:
                log_test("Orchestrator logs", True, "No recent errors detected")
        else:
            log_test("Orchestrator logs", False, "Could not read logs")
    
    return True


def test_firewall_access():
    """Test 6: Firewall & External Access."""
    log_section("Test 6: Firewall & External Access", "🔒")
    
    # Check ufw status
    success, stdout, stderr = run_command(["sudo", "ufw", "status", "verbose"])
    if success:
        print(f"{CYAN}Firewall Status:{NC}")
        print(stdout)
        
        # Check required rules
        required_rules = {
            "22/tcp": "SSH",
            "80/tcp": "HTTP",
            "443/tcp": "HTTPS",
        }
        
        all_configured = True
        for rule, description in required_rules.items():
            if rule in stdout and "ALLOW" in stdout:
                log_test(f"Firewall: {description} ({rule})", True)
            else:
                log_test(f"Firewall: {description} ({rule})", False, "Rule not found or not ALLOW")
                all_configured = False
        
        return all_configured
    else:
        log_test("Firewall status check", False, stderr[:100])
        return False


def test_vault_structure():
    """Test 7: Vault Directory Structure."""
    log_section("Test 7: Vault Directory Structure", "📁")
    
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
        "heagent-dashboard",
        "platinum/odoo",
        "platinum/logs",
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        full_path = VAULT_PATH / dir_path
        exists = full_path.exists()
        log_test(f"Directory: {dir_path}", exists)
        if not exists:
            all_exist = False
    
    return all_exist


def test_odoo_connectivity():
    """Test 8: Odoo JSON-RPC Connectivity."""
    log_section("Test 8: Odoo JSON-RPC Connectivity", "🔗")
    
    odoo_db = os.getenv("ODOO_DB", "postgres")
    odoo_user = os.getenv("ODOO_USER", "odoo")
    odoo_password = os.getenv("ODOO_PASSWORD", "")
    
    if not odoo_password:
        log_test("Odoo password configured", False, "ODOO_PASSWORD not set", critical=True)
        return False
    
    log_test("Odoo password configured", True)
    
    # Test Odoo JSON-RPC authentication
    import json as json_module
    
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "id": 1,
        "params": {
            "service": "common",
            "method": "authenticate",
            "args": [odoo_db, odoo_user, odoo_password, {}]
        }
    }
    
    try:
        request = Request(f"{ODOO_URL}/jsonrpc", method='POST')
        request.add_header('Content-Type', 'application/json')
        request.add_header('User-Agent', 'Phase1-Health-Check/1.0')
        
        data = json_module.dumps(payload).encode('utf-8')
        start_time = time.time()
        
        with urlopen(request, data=data, timeout=30) as response:
            response_time = int((time.time() - start_time) * 1000)
            result = json_module.loads(response.read().decode('utf-8'))
            
            if "error" in result:
                error_msg = result["error"].get("message", "Unknown error")
                log_test("Odoo authentication", False, f"RPC Error: {error_msg}", critical=True)
                return False
            
            uid = result.get("result")
            if uid:
                log_test("Odoo authentication", True, f"UID: {uid} ({response_time}ms)", critical=True)
            else:
                log_test("Odoo authentication", False, "Authentication returned null UID", critical=True)
                return False
    except Exception as e:
        log_test("Odoo authentication", False, str(e)[:100], critical=True)
        return False
    
    return True


def generate_report():
    """Generate Go/No-Go Report."""
    log_section("PHASE 1 VERIFICATION REPORT", "📊")
    
    # Count results
    total_tests = len(test_results["tests"])
    passed_tests = sum(1 for t in test_results["tests"] if t["passed"])
    critical_tests = [t for t in test_results["tests"] if t["critical"] and not t["passed"]]
    
    # Determine Go/No-Go
    if critical_tests:
        test_results["go_no_go"] = "NO-GO"
        status_color = RED
        status_icon = "❌"
    elif passed_tests == total_tests:
        test_results["go_no_go"] = "GO"
        status_color = GREEN
        status_icon = "✅"
    else:
        test_results["go_no_go"] = "GO WITH WARNINGS"
        status_color = YELLOW
        status_icon = "⚠️"
    
    # Print summary
    print(f"{BLUE}Test Summary:{NC}")
    print(f"  Total Tests:  {total_tests}")
    print(f"  {GREEN}Passed:{NC}       {passed_tests}")
    print(f"  {RED}Failed:{NC}       {total_tests - passed_tests}")
    print(f"  {RED}Critical:{NC}     {len(critical_tests)}")
    print()
    
    # Print Go/No-Go decision
    print(f"{BLUE}{'=' * 70}{NC}")
    print(f"{status_color}{status_icon}  PHASE 1 STATUS: {test_results['go_no_go']:^42}{NC}")
    print(f"{BLUE}{'=' * 70}{NC}")
    print()
    
    if critical_tests:
        print(f"{RED}Critical Failures (Must Fix Before Phase 2):{NC}")
        for test in critical_tests:
            print(f"  ❌ {test['name']}")
            if test['details']:
                print(f"     {test['details']}")
        print()
    
    # Save report to file
    report_path = VAULT_PATH / "platinum" / "PHASE1_VERIFICATION_REPORT.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, "w") as f:
        json.dump(test_results, f, indent=2)
    
    print(f"{CYAN}Report saved to:{NC} {report_path}")
    print()
    
    # Recommendations
    if test_results["go_no_go"] == "GO":
        print(f"{GREEN}✅ All critical tests passed! Ready for Phase 2 (Vault Sync).{NC}")
        print()
        print("Next Steps:")
        print("  1. Review any non-critical failures")
        print("  2. Proceed to Phase 2: Implement sync_manager.py")
        print("  3. Configure Git-based vault synchronization")
        print("  4. Implement claim-by-move logic")
    elif test_results["go_no_go"] == "GO WITH WARNINGS":
        print(f"{YELLOW}⚠️ Non-critical issues detected. Can proceed to Phase 2 with caution.{NC}")
        print()
        print("Recommendations:")
        print("  1. Fix non-critical issues when possible")
        print("  2. Monitor logs for recurring warnings")
        print("  3. Proceed to Phase 2 after addressing critical items")
    else:
        print(f"{RED}❌ Critical failures detected. DO NOT proceed to Phase 2.{NC}")
        print()
        print("Required Actions:")
        print("  1. Fix all critical failures listed above")
        print("  2. Re-run verification: python3 platinum/deploy/test_phase1.py")
        print("  3. Only proceed to Phase 2 when status is GO")
    
    print()
    
    return test_results["go_no_go"]


def main():
    """Run all verification tests."""
    print(f"\n{GREEN}{'=' * 70}{NC}")
    print(f"{GREEN}{'🚀 PLATINUM PHASE 1: FINAL VERIFICATION':^66}{NC}")
    print(f"{GREEN}{'=' * 70}{NC}")
    print()
    print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
    print(f"Vault Path: {VAULT_PATH}")
    print(f"VM IP: {os.getenv('VM_IP', 'Not configured')}")
    print(f"Odoo URL: {ODOO_URL}")
    print(f"Dashboard URL: {DASHBOARD_URL}")
    print()
    
    # Run all tests
    tests = [
        ("VM Connectivity", test_vm_connectivity),
        ("PM2 Services", test_pm2_services),
        ("Docker Containers", test_docker_containers),
        ("Health Endpoints", test_health_endpoints),
        ("Watcher Logs", test_watcher_logs),
        ("Firewall Access", test_firewall_access),
        ("Vault Structure", test_vault_structure),
        ("Odoo Connectivity", test_odoo_connectivity),
    ]
    
    for name, test_func in tests:
        try:
            test_func()
        except Exception as e:
            log_test(f"{name} (test execution)", False, f"Exception: {e}", critical=True)
    
    # Generate final report
    go_no_go = generate_report()
    
    # Exit with appropriate code
    if go_no_go == "GO":
        sys.exit(0)
    elif go_no_go == "GO WITH WARNINGS":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
