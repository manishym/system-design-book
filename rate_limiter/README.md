# Rate Limiter MVP

## Overview
A high-performance rate limiting system that controls API request rates using various algorithms like Token Bucket, Sliding Window, and Fixed Window. This MVP demonstrates distributed rate limiting with Redis backend and multiple rate limiting strategies.

## Technology Stack
- **Backend**: Go (Golang)
- **Cache/Storage**: Redis for distributed rate limiting
- **Algorithms**: Token Bucket, Sliding Window, Fixed Window
- **Database**: PostgreSQL for configuration and analytics

## Key Features

### Core Functionality
- [ ] Multiple rate limiting algorithms
- [ ] Distributed rate limiting across multiple servers
- [ ] Per-user and per-API endpoint rate limiting
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

## Database Schema

### Rate Limit Rules Table
```sql
- id (UUID)
- name (string)
- resource_type (enum: user, ip, api_key, endpoint)
- resource_id (string)
- algorithm (enum: token_bucket, fixed_window, sliding_window)
- limit_count (int)
- window_size (int) -- seconds
- burst_capacity (int, nullable)
- is_active (boolean)
- created_at (timestamp)
- updated_at (timestamp)
```

### Rate Limit Logs Table
```sql
- id (UUID)
- resource_type (string)
- resource_id (string)
- endpoint (string)
- allowed (boolean)
- current_count (int)
- limit_count (int)
- remaining (int)
- reset_time (timestamp)
- ip_address (string)
- user_agent (string)
- created_at (timestamp)
```

### Whitelist/Blacklist Table
```sql
- id (UUID)
- type (enum: whitelist, blacklist)
- resource_type (enum: ip, user_id, api_key)
- resource_value (string)
- reason (text)
- expires_at (timestamp, nullable)
- is_active (boolean)
- created_at (timestamp)
```

## Implementation Details

### Token Bucket Algorithm
```go
type TokenBucket struct {
    Capacity     int
    Tokens       int
    RefillRate   int // tokens per second
    LastRefill   time.Time
    mutex        sync.Mutex
}

func (tb *TokenBucket) Allow(tokens int) bool {
    tb.mutex.Lock()
    defer tb.mutex.Unlock()
    
    tb.refill()
    
    if tb.Tokens >= tokens {
        tb.Tokens -= tokens
        return true
    }
    return false
}
```

### Redis Keys Structure
```
rate_limit:{algorithm}:{resource_type}:{resource_id}:{window}
rate_limit:token_bucket:user:user123:60
rate_limit:fixed_window:ip:192.168.1.1:3600
rate_limit:sliding_window:api_key:key456:300
```

### Sliding Window Implementation
```go
func (rl *RateLimiter) CheckSlidingWindow(key string, limit int, window time.Duration) (bool, error) {
    now := time.Now()
    windowStart := now.Add(-window)
    
    pipe := rl.redis.Pipeline()
    
    // Remove old entries
    pipe.ZRemRangeByScore(key, "0", fmt.Sprintf("%d", windowStart.UnixNano()))
    
    // Count current requests
    pipe.ZCard(key)
    
    // Add current request
    pipe.ZAdd(key, &redis.Z{
        Score:  float64(now.UnixNano()),
        Member: fmt.Sprintf("%d", now.UnixNano()),
    })
    
    // Set expiration
    pipe.Expire(key, window)
    
    results, err := pipe.Exec()
    if err != nil {
        return false, err
    }
    
    count := results[1].(*redis.IntCmd).Val()
    return count < int64(limit), nil
}
```

## Rate Limiting Strategies

### Per-User Limits
```yaml
users:
  free_tier:
    requests_per_minute: 100
    requests_per_hour: 1000
    requests_per_day: 10000
  premium_tier:
    requests_per_minute: 1000
    requests_per_hour: 10000
    requests_per_day: 100000
```

### Per-Endpoint Limits
```yaml
endpoints:
  "/api/search":
    requests_per_second: 10
    burst_capacity: 20
  "/api/upload":
    requests_per_minute: 5
    max_file_size: "10MB"
```

### IP-based Limits
```yaml
ip_limits:
  default:
    requests_per_minute: 60
  suspicious_activity:
    requests_per_minute: 10
```

## Configuration Examples

### Rate Limit Rules
```json
{
  "name": "API User Rate Limit",
  "resource_type": "user",
  "resource_id": "*",
  "algorithm": "token_bucket",
  "limit_count": 1000,
  "window_size": 3600,
  "burst_capacity": 100,
  "is_active": true
}
```

### Complex Rule with Conditions
```json
{
  "name": "Premium User Higher Limits",
  "resource_type": "user",
  "conditions": {
    "user_type": "premium",
    "endpoint_prefix": "/api/premium"
  },
  "algorithm": "sliding_window",
  "limit_count": 5000,
  "window_size": 3600,
  "is_active": true
}
```

## Monitoring and Analytics

### Key Metrics
- Requests allowed vs denied
- Rate limit hit frequency
- Average response times
- Top rate-limited users/IPs
- Algorithm performance comparison

### Alert Conditions
- High rate limit violation rates
- Unusual traffic patterns
- System performance degradation
- Redis connection issues

## HTTP Headers

### Standard Rate Limit Headers
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1640995200
X-RateLimit-Retry-After: 60
```

### Custom Headers
```
X-RateLimit-Algorithm: token_bucket
X-RateLimit-Burst-Capacity: 100
X-RateLimit-Window: 3600
```

## Performance Optimizations

### 1. Redis Optimizations
- Use Redis pipelining for batch operations
- Implement connection pooling
- Use Redis Cluster for horizontal scaling

### 2. Algorithm Optimizations
- Choose appropriate algorithm for use case
- Optimize memory usage for sliding window
- Use approximation algorithms when exact precision isn't needed

### 3. Caching Strategies
- Cache rate limit rules in memory
- Use local caches for frequently accessed data
- Implement write-through caching

## Error Handling

### Rate Limit Exceeded Response
```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests",
  "retry_after": 60,
  "limit": 1000,
  "remaining": 0,
  "reset_time": "2024-01-01T12:00:00Z"
}
```

### System Error Response
```json
{
  "error": "rate_limiter_unavailable",
  "message": "Rate limiting service temporarily unavailable",
  "fallback_action": "allow"
}
```

## Getting Started

1. Clone the repository
2. Install Go dependencies: `go mod tidy`
3. Set up Redis server
4. Set up PostgreSQL for configuration storage
5. Configure rate limiting rules
6. Start the service: `go run main.go`

## Configuration File
```yaml
# config.yaml
redis:
  host: localhost
  port: 6379
  password: ""
  db: 0
  max_retries: 3

database:
  host: localhost
  port: 5432
  dbname: rate_limiter
  user: postgres
  password: ""

rate_limiter:
  default_algorithm: token_bucket
  enable_analytics: true
  cleanup_interval: 300 # seconds
  fallback_action: deny # or allow

algorithms:
  token_bucket:
    max_burst_multiplier: 2
  sliding_window:
    cleanup_threshold: 1000
  fixed_window:
    jitter_percent: 10
```

## API Usage Examples

### Check Rate Limit
```bash
curl -X POST "http://localhost:8080/ratelimit/check" \
  -H "Content-Type: application/json" \
  -d '{
    "resource_type": "user",
    "resource_id": "user123",
    "endpoint": "/api/search",
    "tokens": 1
  }'
```

### Create Rate Limit Rule
```bash
curl -X POST "http://localhost:8080/ratelimit/rules" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Search API Limit",
    "resource_type": "endpoint",
    "resource_id": "/api/search",
    "algorithm": "sliding_window",
    "limit_count": 100,
    "window_size": 60,
    "is_active": true
  }'
```

## Load Testing

### Test Scenarios
- Single user high frequency requests
- Multiple users concurrent requests
- Burst traffic simulation
- Long-running sustained load

### Benchmarking
```bash
# Using Apache Bench
ab -n 10000 -c 100 http://localhost:8080/ratelimit/check

# Using custom load test
go run loadtest/main.go -users=1000 -requests=10000 -duration=60s
```

## Future Enhancements
- Machine learning-based adaptive rate limiting
- Geographic rate limiting
- Integration with API gateways (Kong, Envoy)
- Real-time rate limit rule updates
- Advanced analytics dashboard
- Support for GraphQL rate limiting
- Circuit breaker integration
- Custom rate limiting middleware 