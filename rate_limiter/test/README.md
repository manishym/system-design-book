# Testing Structure

This directory contains the organized testing infrastructure for the rate limiter project.

## Directory Structure

```
test/
├── README.md                    # This file
├── test-ci-locally.sh          # Local CI simulation script
├── integration/                # Integration tests
│   ├── integration_test.go     # Integration test suite
│   └── run-integration-tests.sh # Integration test runner
└── chaos/                      # Chaos engineering tests  
    └── chaos-test.sh           # Chaos testing script
```

**Note**: Unit tests (`main_test.go`) remain in the project root directory as they need to be in the same package as `main.go` for Go testing conventions.

## Test Types

### 1. Unit Tests
**Location**: `../main_test.go` (project root)  
**Purpose**: Test individual components and functions in isolation  
**Coverage**: 73.3% code coverage with 12 comprehensive test functions

**Run unit tests:**
```bash
# From rate_limiter directory
go test -v -cover .
go test -v -race -coverprofile=coverage.out .
go tool cover -html=coverage.out -o coverage.html
```

### 2. Integration Tests
**Location**: `integration/`  
**Purpose**: Test end-to-end functionality and system behavior  
**Coverage**: App lifecycle, crash recovery, Redis failures, concurrent load

**Run integration tests:**
```bash
# All integration tests
./test/integration/run-integration-tests.sh

# Quick mode (for CI)
./test/integration/run-integration-tests.sh --quick

# Memory leak tests only
./test/integration/run-integration-tests.sh --memory-only
```

### 3. Kubernetes Integration Tests
**Location**: `../test-kind-locally.sh` (project root)  
**Purpose**: Test Kind (Kubernetes in Docker) cluster setup and deployment  
**Coverage**: Full CI workflow simulation with Kind cluster

**Test Kind cluster setup:**
```bash
# From rate_limiter directory
./test-kind-locally.sh
```

**Prerequisites:**
- Docker installed and running
- Kind CLI installed (`brew install kind` or [installation guide](https://kind.sigs.k8s.io/docs/user/quick-start/#installation))
- kubectl installed
- Helm installed

This script simulates the exact same environment as the GitHub Actions workflow and helps debug Kind cluster issues locally.

**Integration test scenarios:**
- ✅ App lifecycle management (startup/shutdown)
- ✅ Process crash recovery and data persistence
- ✅ Redis failure scenarios and recovery
- ✅ Concurrent load testing (10 users × 20 requests)
- ✅ Data persistence across restarts
- ✅ Failover and graceful degradation

### 3. Chaos Tests
**Location**: `chaos/`  
**Purpose**: Test system resilience under random failure conditions  
**Coverage**: Random app kills, Redis outages, network delays, memory pressure

**Run chaos tests:**
```bash
# Full chaos test (5 minutes)
./test/chaos/chaos-test.sh

# Quick chaos test (1 minute)
./test/chaos/chaos-test.sh --quick

# Intense chaos test (15 minutes)
./test/chaos/chaos-test.sh --intense
```

**Chaos events simulated:**
- 💥 Random application kills and restarts
- 🔄 Redis container restarts
- ⏹️ Redis stops and starts
- 🧠 Memory pressure simulation
- 🌐 Network delay simulation
- 🔍 Continuous system validation

### 4. Local CI Simulation
**Location**: `test-ci-locally.sh`  
**Purpose**: Simulate the complete CI/CD pipeline locally  
**Coverage**: Unit tests + coverage + integration tests + basic app testing

**Run local CI:**
```bash
./test/test-ci-locally.sh
```

## CI/CD Integration

The GitHub Actions workflow includes three stages:

1. **Unit Tests** - Fast component testing with coverage validation
2. **Integration Tests** - Kubernetes deployment validation  
3. **Advanced Integration Tests** - App lifecycle + chaos testing

**Workflow triggers:**
- Pull requests to `main` branch
- Pushes to `main` branch
- Changes to `rate_limiter/` directory
- Changes to workflow files

## Test Requirements

### For Pull Requests
- ✅ All unit tests must pass
- ✅ Code coverage ≥ 70%
- ✅ Integration tests must pass
- ✅ Chaos tests must complete successfully

### Prerequisites
- Docker (for Redis containers)
- Go 1.21+ 
- Redis access (automated via Docker)

## Test Data and Cleanup

All tests include proper setup and cleanup:
- **Redis containers**: Automatically started/stopped per test
- **Test binaries**: Built and cleaned up automatically  
- **Test data**: Isolated per test with unique keys
- **Background processes**: Properly terminated

## Performance Benchmarks

### Unit Tests
- **Duration**: ~30 seconds
- **Coverage**: 73.3%
- **Success Rate**: 100%

### Integration Tests  
- **Duration**: ~60 seconds (quick mode)
- **Success Rate**: 100% (200/200 concurrent requests)
- **Recovery Time**: < 10 seconds for all failure scenarios

### Chaos Tests
- **Duration**: 60 seconds (quick mode), 300 seconds (default)
- **Events**: 5-15 chaos events per minute
- **Resilience**: 100% recovery rate

## Troubleshooting

### Common Issues

**Unit tests fail:**
```bash
# Ensure you're in the right directory
cd /path/to/rate_limiter
go test -v .
```

**Integration tests fail:**
```bash
# Check Docker is running
docker ps

# Check Redis port availability  
netstat -ln | grep 6380
```

**Chaos tests timeout:**
```bash
# Check system resources
docker stats
ps aux | grep rate-limiter
```

**Kind cluster tests fail:**
```bash
# Check prerequisites are installed
kind version
kubectl version --client
helm version

# Check Docker is running
docker ps

# Clean up any existing Kind clusters
kind delete cluster --name kind

# Run with verbose output
./test-kind-locally.sh
```

**Common Kind cluster issues:**
- `ERROR: no nodes found for cluster "kind"` - Cluster failed to start, check Docker resources
- Port conflicts - Ensure ports 8080, 6379 are not in use
- Image load failures - Check Docker image build succeeded
- Pod crash loops - Check application logs with `kubectl logs -l app=rate-limiter`

### Debug Mode

Enable verbose logging:
```bash
# Unit tests
go test -v -race .

# Integration tests
./test/integration/run-integration-tests.sh --quick

# Kind cluster debug
kubectl get events --sort-by=.metadata.creationTimestamp
kubectl logs -l app=rate-limiter --tail=100

# Chaos tests with minimal duration
CHAOS_DURATION=30 ./test/chaos/chaos-test.sh
```

## Contributing

When adding new tests:

1. **Unit tests**: Add to `main_test.go` in project root
2. **Integration tests**: Add to `test/integration/integration_test.go`
3. **Chaos scenarios**: Add to `test/chaos/chaos-test.sh`
4. **Update documentation**: Update this README and main project README

All tests should:
- Include proper setup/cleanup
- Be deterministic and repeatable
- Include meaningful assertions
- Handle timeouts gracefully
- Clean up resources on failure 