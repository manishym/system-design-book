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