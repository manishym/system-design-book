# Design a Rate Limiter

## Context and scope

### The problem
A rate limiter is used to limit api request according to limiting rules. For example for a specific user the number of request per minute might be limited to 600. These kind of limiters are used to protect the application server from being used unfairly.

### System Boundaries
1. API rate limiter sits behind load balancer and before application server
2. It can have multiple micro services for concurrency and load balancing.
3. The request might be screened by any instance of rate limiter, but the rules will still apply.
4. Rate limiter does not handle authentication, creating rules, validating data etc. Those have to be done by other services.

## Goals and Non Goals

### Goals
#### Functional
1. Per user configurable rules. Can be per user per api etc etc.

#### Non functional
1. Should scale to billions of users.
2. State should be shared between instances.
3. Should or should not allow burst traffic (based on requirement)

### Non goals
1. Load balancing application requests (this is left to application load balancer)
2. Authentication, session etc etc, which are not functional requirements for rate limiter.

## API
### Configuration
```json
{
    "ratelimit" : {
        "user": "foo",
        "limits" [{
            "endpoint": POST /tweet,
            "initial_limit": 10,
            "interval": 2s,
            "refill": 1,
        },
        {
            "endpoint": GET /tweet/:id,
            "initial_limit": 100,
            "interval": 2s,
            "refill": 25,
        }
        
        ]

    }

}
```