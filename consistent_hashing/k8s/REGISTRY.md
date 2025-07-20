# Local Container Registry for K3s

This directory contains the configuration for deploying a local container registry inside your K3s cluster. The registry is exposed as a NodePort service for easy access from outside the cluster.

## 📁 Files

- `registry-namespace.yaml` - Namespace for the registry
- `registry-storage.yaml` - Persistent volume claim for registry data
- `registry-deployment.yaml` - Registry deployment and ClusterIP service
- `registry-nodeport.yaml` - NodePort service for external access
- `registry-kustomization.yaml` - Kustomization file for deployment

## 🚀 Quick Start

### 1. Deploy the Registry

```bash
# Deploy all components
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl apply -f k8s/registry-namespace.yaml \
              -f k8s/registry-storage.yaml \
              -f k8s/registry-deployment.yaml \
              -f k8s/registry-nodeport.yaml

# Check status
kubectl get all -n container-registry
```

### 2. Wait for Registry to Start

```bash
# Wait for pod to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=container-registry -n container-registry --timeout=300s

# Test registry access
curl http://localhost:32000/v2/
```

### 3. Use with Build Script

```bash
# Build and push to local registry
PUSH=true ./build-with-registry.sh

# Build, push, and deploy using local registry
PUSH=true DEPLOY=true ./build-with-registry.sh
```

## 🔧 Configuration

### Registry Settings

The registry is configured with:

- **Port**: 5000 (internal), 32000 (NodePort)
- **Storage**: 10Gi persistent volume
- **Location**: `/var/lib/registry` inside the pod
- **Protocol**: HTTP (for local development)

### Environment Variables

| Variable | Value | Description |
|----------|-------|-------------|
| `REGISTRY_STORAGE_FILESYSTEM_ROOTDIRECTORY` | `/var/lib/registry` | Storage location |
| `REGISTRY_STORAGE_DELETE_ENABLED` | `true` | Allow image deletion |
| `REGISTRY_LOG_LEVEL` | `info` | Logging level |
| `REGISTRY_HTTP_ADDR` | `0.0.0.0:5000` | Bind address |

## 🌐 Access Methods

### From Host Machine

```bash
# Registry API
curl http://localhost:32000/v2/

# List repositories
curl http://localhost:32000/v2/_catalog

# List tags for a repository
curl http://localhost:32000/v2/consistent-hashing/gateway/tags/list
```

### From Inside K3s Cluster

```bash
# Using ClusterIP service
registry-service.container-registry.svc.cluster.local:5000
```

## 📦 Docker Operations

### Push Images

```bash
# Tag for local registry
docker tag myimage:latest localhost:32000/myimage:latest

# Push to registry
docker push localhost:32000/myimage:latest
```

### Pull Images

```bash
# Pull from local registry
docker pull localhost:32000/myimage:latest
```

### List Images

```bash
# Get catalog
curl -s http://localhost:32000/v2/_catalog | jq .

# Get tags for specific image
curl -s http://localhost:32000/v2/myimage/tags/list | jq .
```

## 🔨 Using with Consistent Hashing System

### Build and Push

```bash
# Build and push using enhanced script
PUSH=true ./build-with-registry.sh
```

### Deploy from Registry

The build script automatically updates deployment manifests to use the local registry:

```yaml
# Before
image: consistent-hashing/gateway:latest
imagePullPolicy: Never

# After (when using local registry)
image: localhost:32000/consistent-hashing/gateway:latest
imagePullPolicy: Always
```

### Manual Deployment

```bash
# Update your deployment manifests
sed -i 's|consistent-hashing/gateway:latest|localhost:32000/consistent-hashing/gateway:latest|g' k8s/gateway-deployment.yaml
sed -i 's|imagePullPolicy: Never|imagePullPolicy: Always|g' k8s/gateway-deployment.yaml

# Deploy
kubectl apply -f k8s/gateway-deployment.yaml
```

## 🛠️ Advanced Usage

### Custom Registry Configuration

Create a ConfigMap for custom registry settings:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: registry-config
  namespace: container-registry
data:
  config.yml: |
    version: 0.1
    log:
      level: info
    storage:
      filesystem:
        rootdirectory: /var/lib/registry
    http:
      addr: 0.0.0.0:5000
    delete:
      enabled: true
```

### Enable HTTPS (Production)

For production use, enable HTTPS with proper certificates:

```yaml
env:
- name: REGISTRY_HTTP_TLS_CERTIFICATE
  value: /certs/tls.crt
- name: REGISTRY_HTTP_TLS_KEY
  value: /certs/tls.key
```

### Authentication

Add basic authentication:

```yaml
env:
- name: REGISTRY_AUTH
  value: htpasswd
- name: REGISTRY_AUTH_HTPASSWD_REALM
  value: Registry Realm
- name: REGISTRY_AUTH_HTPASSWD_PATH
  value: /auth/htpasswd
```

## 📊 Monitoring

### Registry Health

```bash
# Check registry health
kubectl get pods -n container-registry
kubectl logs deployment/container-registry -n container-registry

# Test connectivity
curl -f http://localhost:32000/v2/ || echo "Registry not accessible"
```

### Storage Usage

```bash
# Check PVC usage
kubectl get pvc -n container-registry

# Check storage usage inside pod
kubectl exec -n container-registry deployment/container-registry -- du -sh /var/lib/registry
```

### Registry Statistics

```bash
# Get repository list
curl -s http://localhost:32000/v2/_catalog | jq '.repositories | length'

# Get all tags for all repositories
for repo in $(curl -s http://localhost:32000/v2/_catalog | jq -r '.repositories[]'); do
  echo "Repository: $repo"
  curl -s http://localhost:32000/v2/$repo/tags/list | jq -r '.tags[]' | sed 's/^/  - /'
done
```

## 🧹 Maintenance

### Cleanup Old Images

```bash
# Delete specific image (if deletion is enabled)
curl -X DELETE http://localhost:32000/v2/myimage/manifests/DIGEST

# Run garbage collection inside container
kubectl exec -n container-registry deployment/container-registry -- registry garbage-collect /etc/docker/registry/config.yml
```

### Backup Registry Data

```bash
# Create backup
kubectl exec -n container-registry deployment/container-registry -- tar -czf /tmp/registry-backup.tar.gz -C /var/lib/registry .

# Copy backup out of pod
kubectl cp container-registry/POD_NAME:/tmp/registry-backup.tar.gz ./registry-backup.tar.gz
```

### Scale Registry

```bash
# Scale up (note: multiple replicas need shared storage)
kubectl scale deployment container-registry --replicas=2 -n container-registry

# Scale down
kubectl scale deployment container-registry --replicas=1 -n container-registry
```

## 🚨 Troubleshooting

### Common Issues

1. **Registry not accessible**
   ```bash
   # Check pod status
   kubectl get pods -n container-registry
   
   # Check logs
   kubectl logs deployment/container-registry -n container-registry
   
   # Check service
   kubectl get svc -n container-registry
   ```

2. **Push/Pull failures**
   ```bash
   # Check if registry accepts HTTP
   curl -v http://localhost:32000/v2/
   
   # Configure Docker for insecure registry (if needed)
   # Add to /etc/docker/daemon.json:
   # {"insecure-registries": ["localhost:32000"]}
   ```

3. **Storage issues**
   ```bash
   # Check PVC status
   kubectl describe pvc registry-data -n container-registry
   
   # Check available storage
   kubectl exec -n container-registry deployment/container-registry -- df -h /var/lib/registry
   ```

4. **Port conflicts**
   ```bash
   # Check if port 32000 is available
   netstat -tulpn | grep 32000
   
   # Use different NodePort if needed
   kubectl patch svc registry-nodeport -n container-registry -p '{"spec":{"ports":[{"port":5000,"nodePort":32001,"targetPort":5000}]}}'
   ```

## 🔐 Security Considerations

### For Development

- HTTP is acceptable for local development
- No authentication required for internal use
- Firewall rules should restrict access to trusted networks

### For Production

- Enable HTTPS with proper certificates
- Implement authentication (htpasswd, LDAP, etc.)
- Use network policies to restrict access
- Regular security updates and monitoring
- Backup and disaster recovery procedures

## 📚 Additional Resources

- [Docker Registry Documentation](https://docs.docker.com/registry/)
- [Kubernetes Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [K3s Private Registry Configuration](https://rancher.com/docs/k3s/latest/en/installation/private-registry/) 