#!/bin/bash

# Integration Test Runner
# This script runs comprehensive integration tests for the rate limiter

set -e

echo "🔥 Starting Integration Tests for Rate Limiter"
echo "=============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}🔧 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Cleanup function
cleanup() {
    echo "🧹 Cleaning up integration test environment..."
    
    # Kill any running rate limiter processes
    pkill -f "rate-limiter-integration" 2>/dev/null || true
    
    # Kill any processes using port 8081 (our test port)
    lsof -ti:8081 | xargs -r kill -9 2>/dev/null || true
    
    # Wait a moment for processes to die
    sleep 2
    
    # Remove test binaries
    rm -f test/integration/rate-limiter-integration
    
    # Stop and remove Redis containers
    docker stop redis-integration-test-6380 2>/dev/null || true
    docker rm redis-integration-test-6380 2>/dev/null || true
    
    # Remove any leftover containers
    docker ps -a | grep "redis-integration-test" | awk '{print $1}' | xargs -r docker rm -f 2>/dev/null || true
    
    print_success "Cleanup completed"
}

# Set trap for cleanup on exit
trap cleanup EXIT

# Check prerequisites
print_step "Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    print_error "Docker is required but not installed"
    exit 1
fi

if ! command -v go &> /dev/null; then
    print_error "Go is required but not installed"
    exit 1
fi

print_success "Prerequisites check passed"

# Check if we're in the right directory and navigate to rate_limiter root
if [ ! -f "main.go" ]; then
    if [ -f "../../main.go" ]; then
        cd ../..
        print_step "Changed to rate_limiter root directory"
    else
        print_error "Cannot find main.go. Please run this script from the rate_limiter directory or test/integration/"
        exit 1
    fi
fi

# Build the application for integration tests
print_step "Building application binary for integration tests..."
go build -o test/integration/rate-limiter-integration .
print_success "Application binary built successfully"

# Run integration tests with different configurations
run_integration_tests() {
    local test_name="$1"
    local algorithm="$2"
    local capacity="$3"
    local rate="$4"
    
    print_step "Running integration tests: $test_name"
    
    # Set environment variables for the test
    export INTEGRATION_ALGORITHM="$algorithm"
    export INTEGRATION_CAPACITY="$capacity"
    export INTEGRATION_RATE="$rate"
    
    # Change to integration test directory
    cd test/integration
    
    # Run the integration tests
    if go test -v -run="TestAppLifecycle|TestAppCrashRecovery|TestRedisFailureScenarios|TestConcurrentLoad|TestDataPersistence|TestFailoverScenarios" -timeout 10m .; then
        print_success "$test_name completed successfully"
        
        # Clean up any remaining processes after test
        pkill -f "rate-limiter-integration" 2>/dev/null || true
        lsof -ti:8081 | xargs -r kill -9 2>/dev/null || true
        sleep 1
        
        cd ../..  # Return to rate_limiter root
        return 0
    else
        print_error "$test_name failed"
        
        # Clean up any remaining processes after failed test
        pkill -f "rate-limiter-integration" 2>/dev/null || true
        lsof -ti:8081 | xargs -r kill -9 2>/dev/null || true
        sleep 1
        
        cd ../..  # Return to rate_limiter root
        return 1
    fi
}

# Run memory leak tests separately (longer duration)
run_memory_tests() {
    print_step "Running memory leak tests (this may take a while)..."
    
    # Change to integration test directory
    cd test/integration
    
    if go test -v -run="TestMemoryLeaks" -timeout 5m .; then
        print_success "Memory leak tests completed successfully"
        cd ../..  # Return to rate_limiter root
        return 0
    else
        print_error "Memory leak tests failed"
        cd ../..  # Return to rate_limiter root
        return 1
    fi
}

# Main test execution
main() {
    local exit_code=0
    
    print_step "Starting comprehensive integration test suite..."
    
    # Test with Token Bucket algorithm
    print_step "Testing with Token Bucket algorithm..."
    if ! run_integration_tests "Token Bucket Tests" "token" "5" "1.0"; then
        exit_code=1
    fi
    
    # Test with Leaky Bucket algorithm
    print_step "Testing with Leaky Bucket algorithm..."
    if ! run_integration_tests "Leaky Bucket Tests" "leaky" "5" "1.0"; then
        exit_code=1
    fi
    
    # Test with different capacity and rate settings
    print_step "Testing with high capacity configuration..."
    if ! run_integration_tests "High Capacity Tests" "token" "20" "5.0"; then
        exit_code=1
    fi
    
    # Run memory leak tests
    if ! run_memory_tests; then
        exit_code=1
    fi
    
    # Summary
    echo ""
    echo "🎯 Integration Test Summary:"
    echo "============================"
    
    if [ $exit_code -eq 0 ]; then
        print_success "All integration tests passed! 🎉"
        echo ""
        echo "✅ App lifecycle management tested"
        echo "✅ Crash recovery scenarios verified"
        echo "✅ Redis failure handling validated"
        echo "✅ Concurrent load testing passed"
        echo "✅ Data persistence confirmed"
        echo "✅ Failover scenarios tested"
        echo "✅ Memory leak tests completed"
        echo ""
        echo "The rate limiter is robust and production-ready!"
    else
        print_error "Some integration tests failed"
        echo ""
        echo "❌ Please check the test output above for details"
        echo "❌ Fix any issues before deploying to production"
    fi
    
    return $exit_code
}

# Show help if requested
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "Integration Test Runner for Rate Limiter"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --help, -h     Show this help message"
    echo "  --quick        Run only essential tests (faster)"
    echo "  --memory-only  Run only memory leak tests"
    echo ""
    echo "This script will:"
    echo "  1. Build the rate limiter binary"
    echo "  2. Start Redis containers for testing"
    echo "  3. Run comprehensive integration tests including:"
    echo "     - App lifecycle management"
    echo "     - Crash recovery scenarios"
    echo "     - Redis failure handling"
    echo "     - Concurrent load testing"
    echo "     - Data persistence verification"
    echo "     - Memory leak detection"
    echo "  4. Clean up all test resources"
    echo ""
    exit 0
fi

# Quick mode for faster CI
if [[ "$1" == "--quick" ]]; then
    print_warning "Running in quick mode (essential tests only)"
    run_integration_tests "Quick Integration Tests" "token" "5" "1.0"
    exit $?
fi

# Memory-only mode
if [[ "$1" == "--memory-only" ]]; then
    print_warning "Running memory tests only"
    run_memory_tests
    exit $?
fi

# Run all tests
main
exit $? 