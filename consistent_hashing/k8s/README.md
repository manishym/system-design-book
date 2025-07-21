# Kubernetes Deployment for Consistent Hashing System

This directory contains Kubernetes manifests for deploying the consistent hashing system in a Kubernetes cluster.

## Architecture

The system consists of:

- **Gateway Service**: StatefulSet with 3 replicas for Raft consensus
- **KV Store Service**: Deployment with auto-scaling (3-10 replicas)
- **Services**: ClusterIP services for internal communication
- **Namespace**: Dedicated namespace for isolation

## Prerequisites

- Kubernetes cluster (v1.19+)
- kubectl configured
- Docker images built and available

## Building Docker Images

From the project root directory:

```bash
# Build images locally
./build.sh

# Build and push to registry
REGISTRY=your-registry.com PUSH=true ./build.sh

# Build, push, and deploy
REGISTRY=your-registry.com PUSH=true DEPLOY=true ./build.sh
```

## Manual Deployment

### 1. Build Docker Images

```bash
# Build Gateway Service
cd gateway
docker build -t consistent-hashing/gateway:latest .
cd ..

# Build KV Store Service  
cd storage/kvstore
docker build -t consistent-hashing/kvstore:latest .
cd ../..
```

### 2. Deploy to Kubernetes

```bash
# Deploy all resources
kubectl apply -k k8s/

# Or deploy individually
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/gateway-deployment.yaml
kubectl apply -f k8s/kvstore-deployment.yaml
```

### 3. Verify Deployment

```bash
# Check pods
kubectl get pods -n consistent-hashing

# Check services
kubectl get svc -n consistent-hashing

# Check gateway ring status
kubectl port-forward svc/gateway-service 8000:8000 -n consistent-hashing
curl http://localhost:8000/ring/status
```

## Configuration

### Environment Variables

#### Gateway Service
- `GATEWAY_ID`: Unique identifier (auto-set from pod name)
- `LISTEN_PORT`: HTTP port (default: 8000)
- `RAFT_PORT`: Raft consensus port (default: 8001)
- `PEER_GATEWAYS`: Other gateway addresses (auto-configured)

#### KV Store Service
- `NODE_ID`: Unique identifier (auto-set from pod name)
- `LISTEN_PORT`: HTTP port (default: 8080)
- `GATEWAY_ADDRESS`: Gateway service address (auto-configured)

### Resource Limits

#### Gateway
- Requests: 256Mi memory, 250m CPU
- Limits: 512Mi memory, 500m CPU
- Storage: 1Gi persistent volume for Raft logs

#### KV Store
- Requests: 128Mi memory, 100m CPU
- Limits: 256Mi memory, 200m CPU
- Auto-scaling: 3-10 replicas based on CPU/memory usage

## Accessing the Services

### From Inside Cluster

```bash
# Gateway service
http://gateway-service.consistent-hashing.svc.cluster.local:8000

# KV Store service
http://kvstore-service.consistent-hashing.svc.cluster.local:8080
```

### From Outside Cluster

```bash
# Port forward for testing
kubectl port-forward svc/gateway-service 8000:8000 -n consistent-hashing
kubectl port-forward svc/kvstore-service 8080:8080 -n consistent-hashing

# Or create LoadBalancer/Ingress services
```

## Testing the Deployment

### 1. Check Gateway Ring Status

```bash
kubectl port-forward svc/gateway-service 8000:8000 -n consistent-hashing &
curl http://localhost:8000/ring/status
```

### 2. Test KV Operations

```bash
kubectl port-forward svc/gateway-service 8000:8000 -n consistent-hashing &

# Find node for a key
curl http://localhost:8000/nodes/test:key1

# Store data (assuming kvstore-xxx-yyy is the responsible node)
kubectl port-forward pod/kvstore-xxx-yyy 8080:8080 -n consistent-hashing &
curl -X POST http://localhost:8080/put \
  -H "Content-Type: application/json" \
  -d '{"key": "test:key1", "value": "hello world"}'

# Retrieve data
curl http://localhost:8080/get/test:key1
```

### 3. Test Auto-scaling

```bash
# Generate load to trigger auto-scaling
kubectl run -i --tty load-generator --rm --image=busybox --restart=Never -- sh

# Inside the pod:
while true; do 
  wget -q -O- http://kvstore-service.consistent-hashing.svc.cluster.local:8080/health
done
```

## Monitoring

### Pod Status

```bash
# Watch pods
kubectl get pods -n consistent-hashing -w

# Check pod logs
kubectl logs -f deployment/kvstore -n consistent-hashing
kubectl logs -f statefulset/gateway -n consistent-hashing
```

### Services

```bash
# Check service endpoints
kubectl get endpoints -n consistent-hashing

# Describe services
kubectl describe svc gateway-service -n consistent-hashing
kubectl describe svc kvstore-service -n consistent-hashing
```

### Auto-scaling

```bash
# Check HPA status
kubectl get hpa -n consistent-hashing
kubectl describe hpa kvstore-hpa -n consistent-hashing
```

## Troubleshooting

### Common Issues

1. **Pods not starting**
   ```bash
   kubectl describe pod <pod-name> -n consistent-hashing
   kubectl logs <pod-name> -n consistent-hashing
   ```

2. **Raft consensus issues**
   ```bash
   # Check gateway logs
   kubectl logs -f statefulset/gateway -n consistent-hashing
   
   # Ensure all 3 gateway pods are running
   kubectl get pods -l app.kubernetes.io/name=gateway -n consistent-hashing
   ```

3. **KV stores not registering**
   ```bash
   # Check gateway connectivity
   kubectl exec -it deployment/kvstore -n consistent-hashing -- \
     curl http://gateway-service:8000/ring/status
   ```

4. **Image pull issues**
   ```bash
   # Check if images exist
   docker images | grep consistent-hashing
   
   # Update image pull policy
   kubectl patch deployment kvstore -n consistent-hashing -p \
     '{"spec":{"template":{"spec":{"containers":[{"name":"kvstore","imagePullPolicy":"Never"}]}}}}'
   ```

### Performance Tuning

1. **Adjust resource limits** based on your workload
2. **Tune auto-scaling metrics** for your traffic patterns  
3. **Increase gateway replicas** for higher availability
4. **Use node affinity** to spread pods across nodes

## Cleanup

```bash
# Delete all resources
kubectl delete -k k8s/

# Or delete namespace (removes everything)
kubectl delete namespace consistent-hashing
```

## Production Considerations

1. **Persistent Storage**: Use proper storage classes for Raft logs
2. **Security**: Add RBAC, network policies, and pod security policies
3. **Monitoring**: Integrate with Prometheus/Grafana
4. **Backup**: Implement backup strategy for Raft logs
5. **Load Balancing**: Use ingress controllers for external access
6. **High Availability**: Spread across multiple availability zones 