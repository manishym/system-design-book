#!/bin/bash

# Enhanced build script for Consistent Hashing System with Local Registry support
set -e

# Configuration
LOCAL_REGISTRY=${LOCAL_REGISTRY:-"localhost:32000"}
REGISTRY=${REGISTRY:-"$LOCAL_REGISTRY"}
TAG=${TAG:-"latest"}
USE_LOCAL_REGISTRY=${USE_LOCAL_REGISTRY:-"true"}

echo "Building Consistent Hashing System..."
echo "Registry: $REGISTRY"
echo "Tag: $TAG"
echo "Use Local Registry: $USE_LOCAL_REGISTRY"

# Function to check if local registry is available
check_local_registry() {
    if curl -s http://$LOCAL_REGISTRY/v2/ > /dev/null 2>&1; then
        echo "✓ Local registry is available at $LOCAL_REGISTRY"
        return 0
    else
        echo "✗ Local registry not available at $LOCAL_REGISTRY"
        return 1
    fi
}

# Build Gateway Service
echo "Building Gateway Service..."
docker build -f gateway/Dockerfile -t ${REGISTRY}/consistent-hashing/gateway:${TAG} .

# Build KV Store Service
echo "Building KV Store Service..."
docker build -f storage/kvstore/Dockerfile -t ${REGISTRY}/consistent-hashing/kvstore:${TAG} .

echo "Build completed successfully!"

# Push to registry if requested
if [ "$PUSH" = "true" ]; then
    echo "Pushing images to registry..."
    
    if [ "$USE_LOCAL_REGISTRY" = "true" ]; then
        if check_local_registry; then
            echo "Pushing to local registry..."
            docker push ${REGISTRY}/consistent-hashing/gateway:${TAG}
            docker push ${REGISTRY}/consistent-hashing/kvstore:${TAG}
            echo "✓ Images pushed to local registry!"
        else
            echo "✗ Local registry not available, skipping push"
            exit 1
        fi
    else
        echo "Pushing to external registry..."
        docker push ${REGISTRY}/consistent-hashing/gateway:${TAG}
        docker push ${REGISTRY}/consistent-hashing/kvstore:${TAG}
        echo "✓ Images pushed to external registry!"
    fi
fi

# Import to K3s if requested (alternative to registry)
if [ "$IMPORT_K3S" = "true" ]; then
    echo "Importing images to K3s containerd..."
    docker save ${REGISTRY}/consistent-hashing/gateway:${TAG} | sudo k3s ctr images import -
    docker save ${REGISTRY}/consistent-hashing/kvstore:${TAG} | sudo k3s ctr images import -
    echo "✓ Images imported to K3s!"
fi

# Deploy to Kubernetes if requested
if [ "$DEPLOY" = "true" ]; then
    echo "Deploying to Kubernetes..."
    
    # Set KUBECONFIG if not already set
    export KUBECONFIG=${KUBECONFIG:-"/etc/rancher/k3s/k3s.yaml"}
    
    # Update deployment manifests to use the correct registry
    if [ "$USE_LOCAL_REGISTRY" = "true" ]; then
        echo "Updating manifests to use local registry..."
        
        # Create temporary manifests with local registry
        mkdir -p /tmp/k8s-deploy
        
        # Update gateway deployment
        sed "s|image: consistent-hashing/gateway:latest|image: ${REGISTRY}/consistent-hashing/gateway:${TAG}|g" \
            k8s/gateway-deployment.yaml > /tmp/k8s-deploy/gateway-deployment.yaml
        sed -i "s|imagePullPolicy: Never|imagePullPolicy: Always|g" /tmp/k8s-deploy/gateway-deployment.yaml
        
        # Update kvstore deployment
        sed "s|image: consistent-hashing/kvstore:latest|image: ${REGISTRY}/consistent-hashing/kvstore:${TAG}|g" \
            k8s/kvstore-deployment.yaml > /tmp/k8s-deploy/kvstore-deployment.yaml
        sed -i "s|imagePullPolicy: Never|imagePullPolicy: Always|g" /tmp/k8s-deploy/kvstore-deployment.yaml
        
        # Copy other files
        cp k8s/namespace.yaml /tmp/k8s-deploy/
        
        # Deploy using temporary manifests
        kubectl apply -f /tmp/k8s-deploy/
        
        # Cleanup
        rm -rf /tmp/k8s-deploy
    else
        # Deploy using original manifests
        kubectl apply -k k8s/
    fi
    
    echo "Deployment completed!"
    
    echo "Waiting for services to be ready..."
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=gateway -n consistent-hashing --timeout=300s
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=kvstore -n consistent-hashing --timeout=300s
    
    echo "Services are ready!"
    echo "Gateway service endpoint:"
    kubectl get svc gateway-service -n consistent-hashing
    echo "KV Store service endpoint:"
    kubectl get svc kvstore-service -n consistent-hashing
fi

# Show usage examples
if [ "$SHOW_EXAMPLES" = "true" ]; then
    echo ""
    echo "=== Usage Examples ==="
    echo ""
    echo "# Deploy local registry first:"
    echo "kubectl apply -f k8s/registry-namespace.yaml -f k8s/registry-storage.yaml -f k8s/registry-deployment.yaml -f k8s/registry-nodeport.yaml"
    echo ""
    echo "# Build and push to local registry:"
    echo "PUSH=true ./build-with-registry.sh"
    echo ""
    echo "# Build and deploy with local registry:"
    echo "PUSH=true DEPLOY=true ./build-with-registry.sh"
    echo ""
    echo "# Use external registry:"
    echo "USE_LOCAL_REGISTRY=false REGISTRY=your-registry.com PUSH=true ./build-with-registry.sh"
    echo ""
    echo "# Test local registry:"
    echo "curl http://localhost:32000/v2/_catalog"
fi 