# Rate Limiter MVP

## Overview
A high-performance rate limiting system that controls API request rates using various algorithms like Token Bucket, Sliding Window, and Fixed Window. This MVP demonstrates distributed rate limiting with Redis backend and multiple rate limiting strategies.

## Technology Stack
- **Backend**: Go (Golang)
- **Cache/Storage**: Redis for distributed rate limiting
- **Algorithms**: Token Bucket, Sliding Window, Fixed Window

## Key Features

### Core Functionality
- [ ] Multiple rate limiting algorithms
- [ ] Distributed rate limiting across multiple servers
- [ ] Dynamic rate limit configuration
- [ ] Rate limit monitoring and analytics
- [ ] Burst capacity handling
- [ ] Whitelist/blacklist support
- [ ] Custom rate limit rules

### API Endpoints
- `POST /ratelimit/check` - Check if request is allowed
- `GET /ratelimit/status/{user_id}` - Get current rate limit status
- `POST /ratelimit/rules` - Create rate limit rule
- `GET /ratelimit/rules` - List rate limit rules
- `PUT /ratelimit/rules/{id}` - Update rate limit rule
- `DELETE /ratelimit/rules/{id}` - Delete rate limit rule
- `GET /ratelimit/analytics` - Get rate limiting analytics

## Rate Limiting Algorithms

### 1. Token Bucket
- Fixed capacity bucket with tokens
- Tokens added at a constant rate
- Each request consumes a token
- Allows burst traffic up to bucket capacity

### 2. Fixed Window
- Count requests in fixed time windows
- Simple to implement and understand
- May allow traffic spikes at window boundaries

### 3. Sliding Window Log
- Maintains log of request timestamps
- Precise rate limiting
- Higher memory usage

### 4. Sliding Window Counter
- Combines fixed window and sliding window
- Approximation of sliding window
- More memory efficient

## Architecture Components

### 1. Rate Limiter Service
- Implements different algorithms
- Handles rate limit checking
- Manages rule configurations

### 2. Redis Manager
- Distributed state management
- Atomic operations for rate limiting
- Efficient key-value operations

### 3. Rule Engine
- Manages rate limiting rules
- Supports complex rule conditions
- Dynamic rule updates

### 4. Analytics Service
- Tracks rate limiting metrics
- Generates reports and insights
- Monitors system performance

## Multi-User Support

The rate limiter now supports multiple users with automatic user creation and individual rate limits:

### Features
- **Automatic User Creation**: New users are automatically added to Redis when they make their first request
- **Default Limits**: New users are initialized with default rate limits (configurable via command line flags)
- **User-Specific Limits**: Individual users can have custom rate limits different from defaults
- **User Management API**: REST endpoints to manage user configurations

### API Endpoints

#### Rate Limiting
```bash
# Check rate limit for a user (auto-creates user if doesn't exist)
GET /check?user_id={user_id}
```

#### User Management
```bash
# Get user information and current limits
GET /users?user_id={user_id}

# Set custom limits for a user (Token Bucket)
POST /users?user_id={user_id}&max_tokens={tokens}&refill_rate={rate}

# Set custom limits for a user (Leaky Bucket)  
POST /users?user_id={user_id}&capacity={capacity}&leak_rate={rate}

# Delete a user and their data
DELETE /users?user_id={user_id}
```

### Usage Examples

#### Basic Rate Limiting
```bash
# First request for new user "alice" - auto-creates with default limits
curl "http://localhost:8080/check?user_id=alice"

# Subsequent requests use the same user's bucket
curl "http://localhost:8080/check?user_id=alice"
```

#### User Management
```bash
# Set custom token bucket limits for alice
curl -X POST "http://localhost:8080/users?user_id=alice&max_tokens=10&refill_rate=2"

# Get alice's current configuration
curl "http://localhost:8080/users?user_id=alice"

# Delete alice's data
curl -X DELETE "http://localhost:8080/users?user_id=alice"
```

### Redis Data Structure

#### User Set
- Key: `ratelimit:users`
- Type: Set
- Contains: List of all user IDs

#### User Configuration
- Key: `ratelimit:users:{user_id}`
- Type: Hash
- Fields:
  - `max_tokens` / `capacity`: Maximum tokens/capacity for the user
  - `refill_rate` / `leak_rate`: Rate for token refill or leaking
  - `created_at`: User creation timestamp
  - `updated_at`: Last configuration update timestamp

#### User Bucket State
- Key: `ratelimit:{algorithm}:{user_id}`
- Type: Hash
- Fields depend on algorithm (tokens/volume, last/last_leak)

## Testing

### Unit Tests

The project includes comprehensive unit tests covering:
- Multi-user rate limiting functionality
- User management API endpoints
- Both Token Bucket and Leaky Bucket algorithms
- Error handling and edge cases
- Redis integration

#### Running Tests Locally

```bash
# Make sure Redis is running (via Docker)
docker run -d --name redis-test -p 6379:6379 redis:alpine

# Run all unit tests with coverage
go test -v -cover .

# Generate detailed coverage report
go test -coverprofile=coverage.out .
go tool cover -html=coverage.out -o coverage.html
```

#### Local CI Simulation

Use the provided script to simulate the full CI pipeline locally:

```bash
# Run the complete CI simulation
./test/test-ci-locally.sh
```

This script will:
- Start Redis container
- Run unit tests with coverage validation (requires ≥70%)
- Build the application
- Run integration tests
- Clean up resources automatically

### CI/CD Pipeline

#### Automated Testing on PRs

Every pull request automatically triggers:

1. **Unit Tests** (`unit-tests` job):
   - Runs on Ubuntu with Go 1.21
   - Starts Redis container for testing
   - Executes full test suite with race detection
   - Validates test coverage (minimum 70% required)
   - Uploads coverage reports as artifacts

2. **Integration Tests** (`integration-tests` job):
   - Runs after unit tests pass
   - Deploys to Kubernetes cluster (KinD)
   - Tests real HTTP endpoints and multi-user functionality
   - Validates Redis connectivity and data persistence

#### Workflow Triggers

Tests run automatically when:
- Opening/updating pull requests to `main` branch
- Pushing to `main` branch  
- Modifying files in `rate_limiter/` directory
- Updating the test workflow itself

#### Test Requirements

- **Coverage**: Minimum 70% code coverage required
- **Race Detection**: All tests run with `-race` flag
- **Redis Integration**: Tests validate actual Redis operations
- **Multi-User**: Comprehensive testing of user isolation and management

### Test Structure

```
main_test.go
├── TestRateLimitHandler_MissingUserID      # Basic error handling
├── TestHealthHandler_*                      # Health endpoint tests  
├── TestTokenBucketIntegration              # Token bucket algorithm
├── TestLeakyBucketIntegration              # Leaky bucket algorithm
├── TestAlgorithmIsolation                  # Algorithm independence
├── TestMultiUserTokenBucket                # Multi-user token bucket
├── TestMultiUserLeakyBucket               # Multi-user leaky bucket
├── TestUserManagementEndpoints            # User API endpoints
├── TestCustomUserLimits                   # Custom user configuration
├── TestUserManagementErrorCases           # Error handling
└── TestLeakyBucketUserManagement          # Leaky bucket user management
```

Each test includes proper setup/teardown and Redis state cleanup to ensure test isolation.

### Integration Tests

Beyond unit tests, the project includes comprehensive integration tests that validate end-to-end functionality and system resilience.

#### Running Integration Tests

```bash
# Run all integration tests
./test/integration/run-integration-tests.sh

# Quick mode for CI (essential tests only)
./test/integration/run-integration-tests.sh --quick

# Memory leak tests only
./test/integration/run-integration-tests.sh --memory-only
```

#### Integration Test Coverage

**App Lifecycle Management:**
- Normal startup and graceful shutdown
- Process crash recovery and data persistence
- Restart behavior and state consistency

**Redis Failure Scenarios:**
- Redis restart during operation
- Connection loss and recovery
- Network partition handling

**Concurrent Load Testing:**
- Multiple users simultaneous requests
- Race condition detection
- Performance under load (90%+ success rate required)

**Data Persistence:**
- User data survives app restart
- Rate limiting state persistence
- Cross-restart consistency validation

**Failover Scenarios:**
- Graceful degradation when Redis is unavailable
- Health endpoint behavior during failures
- Automatic recovery mechanisms

#### Chaos Testing

For ultimate resilience validation, use the chaos testing script:

```bash
# Run chaos testing (5 minutes by default)
./test/chaos/chaos-test.sh

# Quick chaos test (1 minute)
./test/chaos/chaos-test.sh --quick

# Intense chaos test (15 minutes)
./test/chaos/chaos-test.sh --intense
```

**Chaos Events Simulated:**
- 💥 Random app kills and restarts
- 🔄 Redis container restarts
- ⏹️ Redis stops and starts
- 🧠 Memory pressure simulation
- 🌐 Network delay simulation
- 🔍 Continuous system validation

The chaos test continuously validates system recovery and reports resilience metrics.

#### CI/CD Integration

The GitHub Actions workflow includes three test stages:

1. **Unit Tests** - Fast, isolated component testing
2. **Integration Tests** - Kubernetes deployment validation  
3. **Advanced Integration Tests** - App lifecycle and chaos testing

All stages must pass before code can be merged to main branch.