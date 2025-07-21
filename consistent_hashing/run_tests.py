#!/usr/bin/env python3
"""
Test runner for the Consistent Hashing System

This script provides various options for running different types of tests.
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n🔄 {description}")
    print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        if result.stdout:
            print(f"Output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed")
        print(f"Error: {e.stderr}")
        return False


def install_test_dependencies():
    """Install test dependencies"""
    test_req_file = Path("tests/requirements-test.txt")
    if test_req_file.exists():
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(test_req_file)]
        return run_command(cmd, "Installing test dependencies")
    else:
        print("⚠️  Test requirements file not found, skipping dependency installation")
        return True


def run_unit_tests(verbose=False, coverage=False):
    """Run unit tests"""
    cmd = [sys.executable, "-m", "pytest", "tests/unit/"]
    
    if verbose:
        cmd.append("-v")
    if coverage:
        cmd.extend(["--cov=gateway", "--cov=storage", "--cov-report=term-missing"])
    
    return run_command(cmd, "Running unit tests")


def run_integration_tests(verbose=False):
    """Run integration tests"""
    cmd = [sys.executable, "-m", "pytest", "tests/e2e/", "-m", "e2e"]
    
    if verbose:
        cmd.append("-v")
    
    return run_command(cmd, "Running integration/e2e tests")


def run_chaos_tests(verbose=False):
    """Run chaos engineering tests"""
    cmd = [sys.executable, "-m", "pytest", "tests/chaos/", "-m", "chaos"]
    
    if verbose:
        cmd.append("-v")
    
    return run_command(cmd, "Running chaos engineering tests")


def run_all_tests(verbose=False, coverage=False):
    """Run all tests"""
    cmd = [sys.executable, "-m", "pytest", "tests/"]
    
    if verbose:
        cmd.append("-v")
    if coverage:
        cmd.extend(["--cov=gateway", "--cov=storage", "--cov-report=term-missing", "--cov-report=html"])
    
    return run_command(cmd, "Running all tests")


def run_quick_tests():
    """Run quick tests (unit tests only)"""
    cmd = [sys.executable, "-m", "pytest", "tests/unit/", "-x", "--tb=short"]
    return run_command(cmd, "Running quick tests (unit only)")


def run_specific_test(test_pattern):
    """Run specific test by pattern"""
    cmd = [sys.executable, "-m", "pytest", "-k", test_pattern, "-v"]
    return run_command(cmd, f"Running tests matching pattern: {test_pattern}")


def check_system_running():
    """Check if the consistent hashing system is running"""
    import requests
    
    try:
        # Check if gateway is accessible
        response = requests.get("http://127.0.0.1:8000/health", timeout=2)
        if response.status_code == 200:
            print("✅ Gateway service is running")
            return True
    except:
        pass
    
    print("⚠️  Gateway service not detected. Some e2e tests may fail.")
    print("   To run the system: kubectl port-forward svc/gateway-service 8000:8000")
    return False


def run_system_validation(basic_ops_only=False, load_test_only=False):
    """Run system validation tests using the new validation module"""
    from tests.system_validation import SystemValidator
    
    validator = SystemValidator()
    
    try:
        # Always check system health first
        print("🔍 Checking system health...")
        if not validator.check_system_health():
            print("❌ System health check failed - services may not be ready")
            return False
        
        if basic_ops_only:
            print("🧪 Running basic operations test...")
            success = validator.test_basic_key_operations()
            return success
        elif load_test_only:
            print("🚀 Running load test...")
            success, rate = validator.run_load_test()
            print(f"Load test success rate: {rate:.2%}")
            return success
        else:
            # Run full validation
            print("🎯 Running full system validation...")
            success = validator.run_full_validation()
            return success
    except Exception as e:
        print(f"❌ System validation failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run tests for Consistent Hashing System")
    parser.add_argument("--install-deps", action="store_true", 
                       help="Install test dependencies")
    parser.add_argument("--unit", action="store_true", 
                       help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", 
                       help="Run integration/e2e tests only")
    parser.add_argument("--chaos", action="store_true", 
                       help="Run chaos engineering tests only")
    parser.add_argument("--all", action="store_true", 
                       help="Run all tests")
    parser.add_argument("--quick", action="store_true", 
                       help="Run quick tests (unit only, fail fast)")
    parser.add_argument("--test", type=str, metavar="PATTERN",
                       help="Run specific test by pattern")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Verbose output")
    parser.add_argument("--coverage", action="store_true", 
                       help="Run with coverage report")
    parser.add_argument("--check-system", action="store_true",
                       help="Check if system is running")
    parser.add_argument("--system-validation", action="store_true",
                       help="Run full system validation (health, basic ops, load test)")
    parser.add_argument("--basic-ops", action="store_true", 
                       help="Run basic operations validation only")
    parser.add_argument("--load-test", action="store_true",
                       help="Run load test validation only")
    
    args = parser.parse_args()
    
    # Change to project directory
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    print("🧪 Consistent Hashing System Test Runner")
    print("=" * 50)
    
    success = True
    
    # Install dependencies if requested
    if args.install_deps:
        success &= install_test_dependencies()
    
    # Check system status if requested
    if args.check_system:
        check_system_running()
    
    # Run system validation tests if requested
    if args.system_validation:
        check_system_running()
        success &= run_system_validation()
    elif args.basic_ops:
        check_system_running()
        success &= run_system_validation(basic_ops_only=True)
    elif args.load_test:
        check_system_running()
        success &= run_system_validation(load_test_only=True)
    
    # Run tests based on arguments
    elif args.unit:
        success &= run_unit_tests(args.verbose, args.coverage)
    elif args.integration:
        check_system_running()
        success &= run_integration_tests(args.verbose)
    elif args.chaos:
        check_system_running()
        success &= run_chaos_tests(args.verbose)
    elif args.all:
        success &= run_all_tests(args.verbose, args.coverage)
    elif args.quick:
        success &= run_quick_tests()
    elif args.test:
        success &= run_specific_test(args.test)
    else:
        # Default: run unit tests
        print("No specific test type specified, running unit tests...")
        success &= run_unit_tests(args.verbose, args.coverage)
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 All tests completed successfully!")
        sys.exit(0)
    else:
        print("💥 Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main() 