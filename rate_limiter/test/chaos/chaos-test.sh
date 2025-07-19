#!/bin/bash

# Chaos Testing Script for Rate Limiter
# This script simulates various failure scenarios to test system resilience

set -e

echo "🔥 CHAOS TESTING - Rate Limiter Resilience Test"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

print_chaos() {
    echo -e "${PURPLE}💥 CHAOS: $1${NC}"
}

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

# Configuration
CHAOS_DURATION=${CHAOS_DURATION:-300}  # 5 minutes by default
APP_PORT="8082"
REDIS_PORT="6381"
REDIS_CONTAINER="redis-chaos-test"
APP_BINARY="./test/chaos/rate-limiter-chaos"
REDIS_ADDR="localhost:$REDIS_PORT"

# Chaos test state
APP_PID=""
REDIS_RUNNING=true
CHAOS_EVENTS=0
TEST_FAILURES=0

# Cleanup function
cleanup() {
    echo ""
    print_step "🧹 Cleaning up chaos test environment..."
    
    # Kill app if running
    if [ ! -z "$APP_PID" ]; then
        kill $APP_PID 2>/dev/null || true
        wait $APP_PID 2>/dev/null || true
    fi
    
    # Stop background test processes
    pkill -f "chaos_user_test" 2>/dev/null || true
    
    # Remove Redis container
    docker stop $REDIS_CONTAINER 2>/dev/null || true
    docker rm $REDIS_CONTAINER 2>/dev/null || true
    
    # Remove test binary
    rm -f $APP_BINARY
    
    print_success "Cleanup completed"
    
    # Show summary
    echo ""
    echo "🎭 CHAOS TEST SUMMARY"
    echo "===================="
    echo "Duration: ${CHAOS_DURATION} seconds"
    echo "Chaos Events: $CHAOS_EVENTS"
    echo "Test Failures: $TEST_FAILURES"
    
    if [ $TEST_FAILURES -eq 0 ]; then
        print_success "🎉 System survived all chaos events!"
        echo "The rate limiter demonstrated excellent resilience."
    else
        print_warning "⚠️  System experienced $TEST_FAILURES failures"
        echo "Consider improving error handling and recovery mechanisms."
    fi
}

# Set trap for cleanup
trap cleanup EXIT

# Start Redis container
start_redis() {
    print_step "Starting Redis container for chaos testing..."
    
    # Clean up existing container
    docker stop $REDIS_CONTAINER 2>/dev/null || true
    docker rm $REDIS_CONTAINER 2>/dev/null || true
    
    docker run -d \
        --name $REDIS_CONTAINER \
        -p $REDIS_PORT:6379 \
        redis:alpine
    
    sleep 3
    REDIS_RUNNING=true
    print_success "Redis started on port $REDIS_PORT"
}

# Build app for chaos testing
build_app() {
    print_step "Building application for chaos testing..."
    go build -o $APP_BINARY .
    print_success "Application built successfully"
}

# Start the rate limiter app
start_app() {
    if [ ! -z "$APP_PID" ]; then
        kill $APP_PID 2>/dev/null || true
        wait $APP_PID 2>/dev/null || true
    fi
    
    print_step "Starting rate limiter app..."
    
    $APP_BINARY \
        --redis-addr=$REDIS_ADDR \
        --algorithm=token \
        --bucket-capacity=10 \
        --rate=2 \
        --port=$APP_PORT &
    
    APP_PID=$!
    sleep 2
    
    # Verify app is running
    if kill -0 $APP_PID 2>/dev/null; then
        print_success "App started with PID $APP_PID"
        return 0
    else
        print_error "Failed to start app"
        return 1
    fi
}

# Test if app is responsive
test_app_health() {
    local timeout=${1:-5}
    local url="http://localhost:$APP_PORT/health"
    
    if timeout $timeout curl -s $url > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Send test requests to the app
send_test_requests() {
    local user_id="chaos_user_$$"
    local count=${1:-5}
    
    for i in $(seq 1 $count); do
        curl -s "http://localhost:$APP_PORT/check?user_id=${user_id}_${i}" > /dev/null 2>&1 || true
        sleep 0.1
    done
}

# Background load generator
start_background_load() {
    (
        while true; do
            send_test_requests 3
            sleep 1
        done
    ) &
    
    LOAD_PID=$!
    print_step "Background load generator started (PID: $LOAD_PID)"
}

# Chaos events
chaos_kill_app() {
    if [ ! -z "$APP_PID" ] && kill -0 $APP_PID 2>/dev/null; then
        print_chaos "Killing rate limiter app (PID: $APP_PID)"
        kill -9 $APP_PID 2>/dev/null || true
        wait $APP_PID 2>/dev/null || true
        APP_PID=""
        CHAOS_EVENTS=$((CHAOS_EVENTS + 1))
        
        # Try to restart after random delay
        sleep $(( (RANDOM % 5) + 1 ))
        
        if start_app; then
            print_success "App restarted successfully after kill"
        else
            print_error "Failed to restart app after kill"
            TEST_FAILURES=$((TEST_FAILURES + 1))
        fi
    fi
}

chaos_restart_redis() {
    print_chaos "Restarting Redis container"
    
    docker restart $REDIS_CONTAINER > /dev/null 2>&1
    REDIS_RUNNING=false
    CHAOS_EVENTS=$((CHAOS_EVENTS + 1))
    
    sleep $(( (RANDOM % 3) + 2 ))  # Random delay 2-4 seconds
    
    # Wait for Redis to be ready
    for i in {1..10}; do
        if docker exec $REDIS_CONTAINER redis-cli ping > /dev/null 2>&1; then
            REDIS_RUNNING=true
            print_success "Redis recovered after restart"
            break
        fi
        sleep 1
    done
    
    if [ "$REDIS_RUNNING" = false ]; then
        print_error "Redis failed to recover after restart"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
}

chaos_stop_redis() {
    if [ "$REDIS_RUNNING" = true ]; then
        print_chaos "Stopping Redis container"
        docker stop $REDIS_CONTAINER > /dev/null 2>&1
        REDIS_RUNNING=false
        CHAOS_EVENTS=$((CHAOS_EVENTS + 1))
        
        # Start it back after random delay
        sleep $(( (RANDOM % 10) + 5 ))  # Random delay 5-14 seconds
        
        docker start $REDIS_CONTAINER > /dev/null 2>&1
        sleep 3
        
        if docker exec $REDIS_CONTAINER redis-cli ping > /dev/null 2>&1; then
            REDIS_RUNNING=true
            print_success "Redis restarted after stop"
        else
            print_error "Redis failed to restart after stop"
            TEST_FAILURES=$((TEST_FAILURES + 1))
        fi
    fi
}

chaos_memory_pressure() {
    print_chaos "Simulating memory pressure"
    
    # Create memory pressure using stress if available, otherwise use dd
    if command -v stress > /dev/null; then
        timeout 10 stress --vm 1 --vm-bytes 512M > /dev/null 2>&1 || true
    else
        # Fallback: create large files to consume disk space temporarily
        dd if=/dev/zero of=/tmp/chaos_memory_$$_1 bs=1M count=100 > /dev/null 2>&1 || true
        dd if=/dev/zero of=/tmp/chaos_memory_$$_2 bs=1M count=100 > /dev/null 2>&1 || true
        sleep 5
        rm -f /tmp/chaos_memory_$$_* 2>/dev/null || true
    fi
    
    CHAOS_EVENTS=$((CHAOS_EVENTS + 1))
    print_success "Memory pressure simulation completed"
}

chaos_network_delay() {
    print_chaos "Simulating network delay (pausing Redis briefly)"
    
    docker pause $REDIS_CONTAINER > /dev/null 2>&1
    sleep $(( (RANDOM % 3) + 1 ))  # Random delay 1-3 seconds
    docker unpause $REDIS_CONTAINER > /dev/null 2>&1
    
    CHAOS_EVENTS=$((CHAOS_EVENTS + 1))
    print_success "Network delay simulation completed"
}

# Validation: Check if the system recovered properly
validate_system() {
    print_step "Validating system state..."
    
    # Check app health
    if test_app_health 10; then
        print_success "App is responsive"
    else
        print_error "App is not responsive"
        TEST_FAILURES=$((TEST_FAILURES + 1))
        return 1
    fi
    
    # Check Redis connectivity
    if docker exec $REDIS_CONTAINER redis-cli ping > /dev/null 2>&1; then
        print_success "Redis is responsive"
    else
        print_error "Redis is not responsive"
        TEST_FAILURES=$((TEST_FAILURES + 1))
        return 1
    fi
    
    # Test basic functionality
    local test_user="validation_user_$$"
    local response=$(curl -s "http://localhost:$APP_PORT/check?user_id=$test_user")
    
    if echo "$response" | grep -q "allowed"; then
        print_success "Rate limiting functionality works"
    else
        print_error "Rate limiting functionality failed"
        TEST_FAILURES=$((TEST_FAILURES + 1))
        return 1
    fi
    
    return 0
}

# Main chaos testing loop
run_chaos_test() {
    local end_time=$(($(date +%s) + CHAOS_DURATION))
    local chaos_events=(
        "chaos_kill_app"
        "chaos_restart_redis" 
        "chaos_stop_redis"
        "chaos_memory_pressure"
        "chaos_network_delay"
    )
    
    print_step "Starting chaos testing for $CHAOS_DURATION seconds..."
    
    # Start background load
    start_background_load
    
    while [ $(date +%s) -lt $end_time ]; do
        # Validate system before chaos
        if ! validate_system; then
            print_warning "System not healthy before chaos event"
        fi
        
        # Random chaos event
        local event_index=$((RANDOM % ${#chaos_events[@]}))
        local chaos_event=${chaos_events[$event_index]}
        
        # Execute chaos event
        $chaos_event
        
        # Wait a bit before next event
        sleep $(( (RANDOM % 10) + 5 ))  # Random delay 5-14 seconds
        
        # Show progress
        local remaining=$((end_time - $(date +%s)))
        echo "⏰ Time remaining: ${remaining}s | Events: $CHAOS_EVENTS | Failures: $TEST_FAILURES"
    done
    
    # Stop background load
    kill $LOAD_PID 2>/dev/null || true
    
    print_step "Chaos testing completed!"
}

# Show help
show_help() {
    echo "Chaos Testing Script for Rate Limiter"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Environment Variables:"
    echo "  CHAOS_DURATION    Duration in seconds (default: 300)"
    echo ""
    echo "Options:"
    echo "  --help, -h        Show this help message"
    echo "  --quick           Run for 60 seconds only"
    echo "  --intense         Run for 900 seconds (15 minutes)"
    echo ""
    echo "This script will:"
    echo "  1. Start Redis and rate limiter"
    echo "  2. Generate background load"
    echo "  3. Randomly execute chaos events:"
    echo "     - Kill and restart the app"
    echo "     - Restart Redis container"
    echo "     - Stop/start Redis"
    echo "     - Simulate memory pressure"
    echo "     - Simulate network delays"
    echo "  4. Validate system recovery after each event"
    echo "  5. Report resilience metrics"
    echo ""
}

# Parse command line arguments
case "$1" in
    --help|-h)
        show_help
        exit 0
        ;;
    --quick)
        CHAOS_DURATION=60
        print_warning "Quick mode: testing for 60 seconds"
        ;;
    --intense)
        CHAOS_DURATION=900
        print_warning "Intense mode: testing for 15 minutes"
        ;;
esac

# Main execution
main() {
    print_step "Initializing chaos testing environment..."
    
    # Check prerequisites
    if ! command -v docker > /dev/null; then
        print_error "Docker is required for chaos testing"
        exit 1
    fi
    
    if [ ! -f "main.go" ]; then
        if [ -f "../../main.go" ]; then
            cd ../..
            print_step "Changed to rate_limiter root directory"
        else
            print_error "Cannot find main.go. Please run this script from the rate_limiter directory or test/chaos/"
            exit 1
        fi
    fi
    
    # Setup
    build_app
    start_redis
    start_app
    
    # Initial validation
    if ! validate_system; then
        print_error "Initial system validation failed"
        exit 1
    fi
    
    print_success "Initial setup completed successfully"
    
    # Run chaos tests
    run_chaos_test
    
    # Final validation
    print_step "Performing final system validation..."
    if validate_system; then
        print_success "Final validation passed - system is resilient!"
    else
        print_error "Final validation failed - system needs improvement"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
}

# Run main function
main "$@"
