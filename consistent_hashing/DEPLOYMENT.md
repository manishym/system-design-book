# Consistent Hashing System - Deployment Guide

This guide covers deploying the consistent hashing system using the new containerized and Kubernetes-ready structure.

## 📁 Project Structure

```
consistent_hashing/
├── gateway/                      # Gateway service
│   ├── Dockerfile               # Gateway container image
│   └── gateway_service.py       # Gateway service code
├── storage/kvstore/             # KV Store service  
│   ├── Dockerfile               # KV Store container image
│   └── kvstore_service.py       # KV Store service code
├── k8s/                         # Kubernetes manifests
│   ├── namespace.yaml           # Namespace definition
│   ├── gateway-deployment.yaml  # Gateway StatefulSet & Services
│   ├── kvstore-deployment.yaml  # KV Store Deployment & HPA
│   ├── kustomization.yaml       # Kustomize configuration
│   └── README.md               # K8s deployment documentation
├── build.sh                    # Build and deployment script
├── example_demo.py             # Demo script (updated for new structure)
├── requirements.txt            # Python dependencies
├── USAGE.md                    # Original usage documentation
└── README.md                   # Project overview
```

## 🚀 Deployment Options

### Option 1: Local Development (Python)

For local development and testing:

```bash
# Terminal 1 - Gateway
cd gateway
python gateway_service.py --gateway-id gateway-1 --port 8000 --raft-port 8001

# Terminal 2 - KV Store
cd storage/kvstore  
python kvstore_service.py --node-id kvstore-A --port 8080 --gateway localhost:8000

# Terminal 3 - Demo
python example_demo.py
```

### Option 2: Docker Compose (Coming Soon)

For local containerized testing:

```bash
# Build images
./build.sh

# Run with Docker Compose
docker-compose up
```

### Option 3: Kubernetes Deployment

For production-ready deployment:

```bash
# Build and deploy in one command
DEPLOY=true ./build.sh

# Or step by step
./build.sh                    # Build images
kubectl apply -k k8s/         # Deploy to K8s
```

## 🐳 Docker Images

### Gateway Service Image

```dockerfile
# From gateway/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY ../requirements.txt .
RUN pip install -r requirements.txt
COPY gateway_service.py .
EXPOSE 8000 8001
CMD python gateway_service.py --gateway-id ${GATEWAY_ID} --port ${LISTEN_PORT}
```

**Environment Variables:**
- `GATEWAY_ID`: Unique gateway identifier
- `LISTEN_PORT`: HTTP API port (default: 8000)
- `RAFT_PORT`: Raft consensus port (default: 8001)
- `PEER_GATEWAYS`: Space-separated list of peer addresses

### KV Store Service Image

```dockerfile
# From storage/kvstore/Dockerfile  
FROM python:3.11-slim
WORKDIR /app
COPY ../../requirements.txt .
RUN pip install -r requirements.txt
COPY kvstore_service.py .
EXPOSE 8080
CMD python kvstore_service.py --node-id ${NODE_ID} --port ${LISTEN_PORT}
```

**Environment Variables:**
- `NODE_ID`: Unique node identifier
- `LISTEN_PORT`: HTTP API port (default: 8080)
- `GATEWAY_ADDRESS`: Gateway service address

## ☸️ Kubernetes Architecture

### Gateway Service (StatefulSet)

```yaml
# 3 replicas for Raft consensus
# Persistent volumes for Raft logs
# Headless service for peer discovery
# LoadBalancer service for client access
```

**Features:**
- Raft consensus for distributed hash ring management
- Persistent storage for consensus logs
- Auto-discovery of peer gateways
- Health checks and readiness probes

### KV Store Service (Deployment)

```yaml  
# 3-10 replicas with auto-scaling
# HPA based on CPU/memory usage
# ClusterIP service for internal access
```

**Features:**
- Horizontal Pod Autoscaler (3-10 replicas)
- Automatic registration with gateway
- Health checks for pod management
- Resource limits and requests

## 🔧 Build Script Usage

The `build.sh` script provides flexible build and deployment options:

```bash
# Build images only
./build.sh

# Build with custom registry
REGISTRY=myregistry.com ./build.sh

# Build and push to registry
REGISTRY=myregistry.com PUSH=true ./build.sh

# Build, push, and deploy to K8s
REGISTRY=myregistry.com PUSH=true DEPLOY=true ./build.sh

# Custom tag
TAG=v1.0.0 ./build.sh
```

## 📊 Monitoring and Observability

### Health Checks

All services include comprehensive health checks:

```bash
# Gateway health
curl http://gateway:8000/ring/status

# KV Store health  
curl http://kvstore:8080/health
```

### Kubernetes Monitoring

```bash
# Pod status
kubectl get pods -n consistent-hashing

# Service endpoints
kubectl get endpoints -n consistent-hashing

# Auto-scaling status
kubectl get hpa -n consistent-hashing

# Logs
kubectl logs -f statefulset/gateway -n consistent-hashing
kubectl logs -f deployment/kvstore -n consistent-hashing
```

## 🔄 Auto-Scaling Configuration

The KV Store service includes sophisticated auto-scaling:

```yaml
spec:
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        averageUtilization: 70
  - type: Resource  
    resource:
      name: memory
      target:
        averageUtilization: 80
```

**Scaling Behavior:**
- Scale up: 50% increase every 60 seconds
- Scale down: 10% decrease every 60 seconds  
- Stabilization: 5 minutes for scale-down, 1 minute for scale-up

## 🔐 Security Considerations

### Container Security

- Non-root user in containers
- Minimal base images (python:3.11-slim)
- Security context restrictions
- Resource limits to prevent resource exhaustion

### Kubernetes Security

- Dedicated namespace for isolation
- Network policies (recommended)
- RBAC for service accounts (recommended)
- Pod security policies (recommended)

## 🚨 Troubleshooting

### Common Issues

1. **Images not found**
   ```bash
   # Check if images are built
   docker images | grep consistent-hashing
   
   # Update image pull policy for local testing
   kubectl patch deployment kvstore -n consistent-hashing -p \
     '{"spec":{"template":{"spec":{"containers":[{"name":"kvstore","imagePullPolicy":"Never"}]}}}}'
   ```

2. **Gateway consensus issues**
   ```bash
   # Ensure all 3 gateway pods are running
   kubectl get pods -l app.kubernetes.io/name=gateway -n consistent-hashing
   
   # Check Raft logs
   kubectl logs gateway-0 -n consistent-hashing
   ```

3. **KV stores not registering**
   ```bash
   # Check gateway connectivity
   kubectl exec -it deployment/kvstore -n consistent-hashing -- \
     curl http://gateway-service:8000/ring/status
   ```

### Performance Tuning

- Adjust resource limits based on workload
- Tune auto-scaling metrics for traffic patterns
- Use node affinity to spread pods across nodes
- Consider increasing gateway replicas for higher availability

## 📈 Production Deployment

### Prerequisites

- Kubernetes cluster with persistent volume support
- Container registry for images
- Monitoring stack (Prometheus/Grafana recommended)
- Log aggregation (ELK/EFK stack recommended)

### Production Checklist

- [ ] Use proper storage classes for Raft logs
- [ ] Implement backup strategy for consensus data
- [ ] Set up monitoring and alerting
- [ ] Configure ingress for external access
- [ ] Implement RBAC and security policies
- [ ] Set up log aggregation
- [ ] Configure resource quotas
- [ ] Plan for disaster recovery

### Scaling Recommendations

| Environment | Gateway Replicas | KV Store Replicas | Resources |
|-------------|------------------|-------------------|-----------|
| Development | 1 | 1-2 | Small |
| Staging | 3 | 2-5 | Medium |
| Production | 3-5 | 5-20 | Large |

## 🔄 Migration from Old Structure

If migrating from the original flat structure:

1. **Update import paths** in custom applications:
   ```python
   # Old
   from gateway_service import GatewayService
   from kvstore_service import KVStoreClient
   
   # New  
   from gateway.gateway_service import GatewayService
   from storage.kvstore.kvstore_service import KVStoreClient
   ```

2. **Update Docker build contexts** if using custom Dockerfiles

3. **Update CI/CD pipelines** to use new structure

## 📚 Additional Resources

- [Kubernetes Documentation](./k8s/README.md) - Detailed K8s deployment guide
- [Usage Guide](./USAGE.md) - Original API and usage documentation  
- [Example Demo](./example_demo.py) - Comprehensive demo script
- [Gateway Service](./gateway/) - Gateway service implementation
- [KV Store Service](./storage/kvstore/) - KV store service implementation 

## CI/CD Fixes and Improvements

### Recent Fixes (July 2025)

#### Gateway Pod Startup Issues
- **Issue**: Gateway pods were timing out during startup in Kind clusters
- **Root Cause**: Import path issues and aggressive startup probe settings
- **Fix**: 
  - Updated gateway service to handle both relative and absolute imports
  - Increased startup probe `failureThreshold` from 30 to 60
  - Increased startup probe `periodSeconds` from 2 to 5 seconds
  - Updated Docker CMD to use environment variables instead of command-line args

#### Environment Variable Handling
- **Issue**: Services not properly reading environment variables in containers
- **Fix**: Updated both gateway and kvstore services to prioritize environment variables over command-line arguments

#### Docker Image Configuration
- **Issue**: Incorrect file copying and naming in Dockerfiles
- **Fix**: 
  - Updated gateway Dockerfile to copy `gateway_service_simple.py` with correct name
  - Simplified CMD to just run the Python script (using env vars)
  - Updated health checks to use correct endpoints

#### GitHub Actions Workflow Improvements  
- **Issue**: CI timeouts and insufficient error reporting
- **Fix**:
  - Increased pod readiness timeout from 300s to 600s (10 minutes)
  - Added better error handling and logging in wait steps
  - Improved pod status reporting during failures

### Testing Locally with Kind

To test the deployment locally with Kind before CI:

```bash
# Run simplified Kind test
./test-simple-kind.sh

# This will:
# 1. Create a single-node Kind cluster
# 2. Build and test Docker images
# 3. Deploy gateway and kvstore (1 replica each)
# 4. Verify pods start and endpoints work
# 5. Clean up automatically
```

### CI/CD Pipeline Status

The GitHub Actions workflow now includes:

1. **Unit Tests** - All 68 tests passing ✅
2. **Integration Tests** - Kind deployment with full validation ✅
3. **Build Validation** - Docker image functionality tests ✅
4. **Chaos Tests** - Node failure and recovery tests ✅
5. **Security Scanning** - Trivy vulnerability scanning ✅

### Environment Variables

Both services now support these environment variables for Kubernetes deployment:

#### Gateway Service
- `GATEWAY_ID` - Unique gateway identifier (set from `metadata.name`)
- `LISTEN_PORT` - Port to listen on (default: 8000)
- `PEER_GATEWAYS` - Space-separated list of peer gateway addresses

#### KVStore Service  
- `NODE_ID` - Unique node identifier (set from `metadata.name`)
- `LISTEN_PORT` - Port to listen on (default: 8080)
- `GATEWAY_ADDRESS` - Gateway service address

### Health Check Endpoints

- **Gateway**: `/ring/status` - Returns hash ring status and statistics
- **KVStore**: `/health` - Returns node health and registration status

Both endpoints return JSON with 200 status when healthy. 