# Design a Rate Limiter

## Context and Scope

### The Problem
A rate limiter is used to enforce API request limits according to predefined rules. For example, a specific user might be allowed no more than 600 requests per minute. These limiters protect backend systems from abuse, ensure fair usage, and provide predictable performance under load.

---

## System Boundaries

### Inside the Boundary
- Stateless Rate Limiter microservice(s)
- Redis (Master + Replicas) used for shared configuration and counters
- Lua scripts for atomic rate-limit checks within Redis
- API exposed for real-time rate-limit checks

### Outside the Boundary
- API Gateway / Load Balancer
- Authentication and Authorization services
- Rule definition and user management systems
- Monitoring, alerting, and analytics pipelines (though logs/metrics are emitted from inside)
- Client retry/backoff behavior

The rate limiter operates **after authentication** and **before application logic**, and only handles request admission based on rate-limit policies.

---

## Goals and Non-Goals

### Goals
#### Functional
1. Support per-user, per-endpoint configurable rate limiting rules.
2. Provide deterministic behavior regardless of which rate limiter instance handles the request.

#### Non-Functional
1. Scalable to billions of users and millions of requests per second.
2. State consistency across instances via Redis.
3. Optional support for bursty traffic (configurable).
4. Fast response: enforce limits within 10 ms (p99).
5. Highly available: 99.99% availability target.

### Non-Goals
1. Does not handle request authentication or identity resolution.
2. Does not load balance application traffic.
3. Does not manage user accounts or define rate-limit rules.

---

## API

### Rate Limit Configuration Schema
Configuration is stored in Redis for low-latency lookup and dynamic updates.

```json
{
  "ratelimit": {
    "user": "foo",
    "limits": [
      {
        "endpoint": "POST /tweet",
        "initial_limit": 10,
        "interval": "2s",
        "refill_rate": 1
      },
      {
        "endpoint": "GET /tweet/:id",
        "initial_limit": 100,
        "interval": "2s",
        "refill_rate": 25
      }
    ]
  }
}
```

#### Notes
- `initial_limit` is the bucket capacity
- `refill_rate` is number of tokens added every `interval`
- `endpoint` can use path templates (e.g., `/tweet/:id`)
- Configuration can be updated dynamically via a side service

---

## Architecture Diagram
(Refer to attached diagram: includes user requests -> API Gateway -> Rate Limiter -> Redis -> App Server)

- The API Gateway forwards incoming requests to one of many Rate Limiter instances.
- Each instance checks limits using atomic Lua script on Redis Master.
- Redis Replicas serve for read fallback; writes go to master.
- Approved requests proceed to App Server.
- Rejected requests are short-circuited at gateway.

---

## Testing and Rollout Plan

### Unit Tests
- Target 85%+ coverage of core logic (token bucket, Redis interactions)
- Run in CI pipeline for every pull request

### Integration Tests
- Deploy on a test Kubernetes cluster with mocked traffic
- Simulate concurrent access to validate race conditions

### Regression and Canary Testing
- Deploy to staging cluster first
- Enable for 1% of production traffic as canary
- Monitor using Prometheus + Alertmanager for error rates and latencies

### Fault Tolerance
- Retry Redis failures with exponential backoff
- Fallback to static config if Redis is down
- Emit logs and metrics to central observability platform

---

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Token Bucket (Current)** | Simple burst support, intuitive | Slight over-allowance possible |
| **Leaky Bucket** | Smooth constant rate | Harder to implement in distributed cache |
| **Client-side rate limiting** | Offloads work | Cannot prevent abuse globally |
| **In-memory limiter with gossip sync** | No Redis dependency | Complex consistency and merge logic |

---

## Conclusion
This design provides a scalable, consistent, and extensible foundation for distributed rate limiting. By leveraging Redis for shared state and atomic operations, the system maintains correctness across multiple instances, handles burst traffic, and integrates smoothly with existing API infrastructure.

