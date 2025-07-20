# CI/CD Workflow for Consistent Hashing System

This directory contains GitHub Actions workflows for automated testing and validation of the consistent hashing system.

## 🚀 Workflows

### `test.yml` - Main Test Pipeline

Comprehensive testing pipeline that validates the system across multiple dimensions:

#### **Jobs Overview:**

1. **Unit Tests** 🧪
   - Runs on every push/PR
   - Tests individual components in isolation
   - Generates coverage reports
   - Fast feedback (< 2 minutes)

2. **Integration Tests** 🔗
   - Tests in real Kind clusters
   - Matrix testing across Kubernetes versions
   - Validates end-to-end functionality
   - Load testing and system validation

3. **Chaos Engineering Tests** 💥
   - Only on main branch pushes
   - Tests system resilience under failure conditions
   - Validates fault tolerance and recovery

4. **Security Scanning** 🔒
   - Trivy vulnerability scanning
   - Results uploaded to GitHub Security tab
   - Runs in parallel with other jobs

5. **Build Validation** 🏗️
   - Validates Docker image builds
   - Tests image functionality
   - Quick smoke tests

## 📊 Test Coverage

### Unit Tests (Job 1)
- **Hash Ring Tests**: 21 tests covering all consistent hashing operations
- **Gateway Service Tests**: 22 tests for API endpoints and node management
- **KV Store Tests**: 25 tests for CRUD operations and networking

### Integration Tests (Job 2)
- **System Deployment**: Full Kubernetes deployment in Kind
- **Service Discovery**: Pod-to-pod communication validation
- **Load Testing**: Concurrent operations stress testing
- **Data Consistency**: Cross-node data validation

### Chaos Tests (Job 3)
- **Node Failures**: Random pod termination and recovery
- **Network Partitions**: Simulated network splits
- **Resource Exhaustion**: Memory and CPU pressure testing
- **Cascading Failures**: Multiple simultaneous failures

## 🏗️ Infrastructure

### Kind Cluster Configuration
```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30000-32000  # NodePort range
- role: worker
- role: worker
```

### Test Matrix
- **Kubernetes Versions**: v1.28.0, v1.27.3
- **Python Version**: 3.11
- **Test Types**: Unit, Integration, Chaos, Security

## 🎯 Trigger Conditions

### Automatic Triggers
- **Push to main/develop**: Full test suite
- **Pull Requests**: Unit + Integration tests
- **Path-based**: Only when consistent_hashing/ files change

### Manual Triggers
- **workflow_dispatch**: Manual execution via GitHub UI
- **Chaos tests**: Only on main branch

## 📈 Performance Benchmarks

### Expected Execution Times
- **Unit Tests**: ~2 minutes
- **Integration Tests**: ~15 minutes per matrix job
- **Chaos Tests**: ~30 minutes
- **Total Pipeline**: ~20-25 minutes

### Success Criteria
- **Unit Tests**: >90% pass rate
- **Load Tests**: >80% success rate for 50 concurrent operations
- **Integration**: All core API endpoints functional
- **Build**: All Docker images build successfully

## 🔧 Configuration

### Environment Variables
```yaml
KIND_VERSION: v0.20.0      # Kind cluster version
KUBECTL_VERSION: v1.28.0   # kubectl version
PYTHON_VERSION: '3.11'     # Python runtime version
```

### Dependencies
- **Testing**: pytest, pytest-cov, requests
- **Infrastructure**: Kind, kubectl, Docker
- **Security**: Trivy scanner

## 📋 Usage Examples

### Running Locally
```bash
# Simulate the CI environment locally
export PYTHONPATH="./consistent_hashing"

# Run unit tests (Job 1)
cd consistent_hashing
python -m pytest tests/unit/ -v --cov=gateway --cov=storage

# Build Docker images (Job 5)
docker build -f gateway/Dockerfile -t consistent-hashing/gateway:test .
docker build -f storage/kvstore/Dockerfile -t consistent-hashing/kvstore:test .
```

### Manual Workflow Trigger
1. Go to GitHub Actions tab
2. Select "Consistent Hashing System Tests"
3. Click "Run workflow"
4. Choose branch and options

## 📊 Artifacts and Reports

### Generated Artifacts
- **Test Results**: JUnit XML reports for all test suites
- **Coverage Reports**: HTML coverage reports with line-by-line analysis
- **Security Scans**: SARIF files uploaded to GitHub Security tab
- **System Logs**: Pod logs and cluster information for debugging

### Artifact Retention
- **Test Results**: 30 days
- **Coverage Reports**: 30 days
- **Security Scans**: Permanent (in Security tab)

## 🚨 Failure Handling

### Automatic Cleanup
- Kind clusters are automatically deleted after each job
- Port forwarding processes are killed on job completion
- Temporary resources are cleaned up

### Debugging Failed Runs
1. Check the "Collect system information" step for cluster state
2. Download artifacts for detailed test results
3. Review pod logs in the workflow output
4. Check security scan results if applicable

## 🔄 Maintenance

### Regular Updates
- **Dependencies**: Update action versions quarterly
- **Kubernetes**: Update Kind node images for new K8s versions
- **Python**: Update Python version for new releases
- **Tools**: Update kubectl, Kind versions as needed

### Monitoring
- **Success Rate**: Monitor overall pipeline success rate
- **Performance**: Track execution time trends
- **Security**: Review security scan results regularly
- **Coverage**: Maintain >85% code coverage

## 🏆 Quality Gates

### Merge Requirements
- ✅ All unit tests pass
- ✅ Integration tests pass on at least one K8s version
- ✅ No high-severity security vulnerabilities
- ✅ Docker images build successfully
- ✅ Code coverage > 85%

### Release Requirements (main branch)
- ✅ All above requirements
- ✅ Chaos tests pass
- ✅ Load tests achieve >90% success rate
- ✅ Full security scan clean

This CI/CD pipeline ensures the consistent hashing system maintains high quality, reliability, and security standards across all development phases. 