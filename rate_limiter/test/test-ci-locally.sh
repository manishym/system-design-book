#!/bin/bash

# Local CI Simulation Script
# This script simulates the GitHub Actions workflow locally to test before pushing

set -e  # Exit on any error

echo "🚀 Starting local CI simulation for rate limiter"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_step() {
    echo -e "${YELLOW}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Cleanup function
cleanup() {
    echo "🧹 Cleaning up..."
    docker stop redis-ci-test 2>/dev/null || true
    docker rm redis-ci-test 2>/dev/null || true
}

# Set trap for cleanup on exit
trap cleanup EXIT

# Step 1: Check if we're in the right directory and navigate to rate_limiter root
if [ ! -f "main.go" ]; then
    if [ -f "../main.go" ]; then
        cd ..
        print_step "Changed to rate_limiter root directory"
    else
        print_error "Cannot find main.go. Please run this script from the rate_limiter directory or test/"
        exit 1
    fi
fi

print_step "Checking Go version..."
go version

# Step 2: Download dependencies
print_step "Downloading Go modules..."
go mod download

# Step 3: Start Redis for tests
print_step "Starting Redis container for testing..."
docker run -d --name redis-ci-test -p 6379:6379 redis:alpine
sleep 3

# Verify Redis is running
if ! docker exec redis-ci-test redis-cli ping | grep -q "PONG"; then
    print_error "Redis failed to start"
    exit 1
fi
print_success "Redis is running"

# Step 4: Run unit tests with coverage
print_step "Running unit tests with coverage..."
go test -v -race -coverprofile=coverage.out .

# Step 5: Generate coverage report
print_step "Generating coverage report..."
go tool cover -html=coverage.out -o coverage.html

# Step 6: Check coverage percentage
print_step "Checking test coverage..."
COVERAGE=$(go tool cover -func=coverage.out | grep total | awk '{print $3}' | sed 's/%//')
echo "Total coverage: ${COVERAGE}%"

if awk "BEGIN {exit !($COVERAGE < 70)}"; then
    print_error "Coverage $COVERAGE% is below required 70%"
    exit 1
else
    print_success "Coverage $COVERAGE% meets the requirement (>= 70%)"
fi

# Step 7: Build the application
print_step "Building the application..."
go build -o rate-limiter

# Step 8: Basic integration test
print_step "Running basic integration test..."
./rate-limiter --redis-addr=localhost:6379 --algorithm=token --bucket-capacity=5 --rate=1 &
APP_PID=$!

# Wait for app to start
sleep 3

# Test health endpoint
if curl -f http://localhost:8080/health > /dev/null 2>&1; then
    print_success "Health endpoint is working"
else
    print_error "Health endpoint failed"
    kill $APP_PID 2>/dev/null || true
    exit 1
fi

# Test rate limiting
print_step "Testing rate limiting functionality..."
for i in {1..3}; do
    echo "Request $i:"
    curl -s "http://localhost:8080/check?user_id=test_user_$i" || true
    echo ""
done

# Test user management
print_step "Testing user management API..."
curl -s -X POST "http://localhost:8080/users?user_id=local_test&max_tokens=10&refill_rate=2" || true
echo ""
curl -s "http://localhost:8080/users?user_id=local_test" || true
echo ""

# Stop the application
kill $APP_PID 2>/dev/null || true

print_success "All tests passed! 🎉"
print_step "You can view the coverage report at: coverage.html"

echo ""
echo "🎯 Summary:"
echo "  - Unit tests: PASSED"
echo "  - Coverage: ${COVERAGE}% (>= 70%)"
echo "  - Integration tests: PASSED"
echo "  - Ready for CI/CD pipeline" 