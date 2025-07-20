#!/bin/bash

# ============================================================================
# Local Workflow Test Runner
# Mirrors the GitHub Actions workflow: consistent-hashing-test.yml
# ============================================================================

set -euo pipefail

# Configuration from workflow YAML
KIND_VERSION="v0.20.0"
KUBECTL_VERSION="v1.28.0"
PYTHON_VERSION="3.11"
KIND_CLUSTER_NAME="consistent-hashing-test"
NAMESPACE="consistent-hashing"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_section() {
    echo -e "\n${BLUE}============================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================================${NC}\n"
}

# Default test selection
RUN_UNIT=true
RUN_INTEGRATION=true
RUN_CHAOS=false
RUN_SECURITY=false
RUN_BUILD=true
SKIP_CLEANUP=false
KIND_NODE_IMAGE="kindest/node:v1.28.0"

# Parse command line arguments
show_help() {
    cat << EOF
Local Workflow Test Runner

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --unit-only         Run only unit tests
    --integration-only  Run only integration tests
    --chaos            Include chaos engineering tests
    --security         Include security scanning
    --no-build         Skip build validation
    --skip-cleanup     Don't cleanup Kind cluster (for debugging)
    --kind-image       Kind node image (default: kindest/node:v1.28.0)
    --help             Show this help message

EXAMPLES:
    $0                           # Run unit, integration, and build tests
    $0 --unit-only               # Run only unit tests
    $0 --integration-only        # Run only integration tests
    $0 --chaos --security        # Run all test types including chaos and security
    $0 --skip-cleanup            # Keep Kind cluster running after tests
    $0 --kind-image kindest/node:v1.27.3  # Use different Kubernetes version

EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --unit-only)
            RUN_INTEGRATION=false
            RUN_BUILD=false
            shift
            ;;
        --integration-only)
            RUN_UNIT=false
            RUN_BUILD=false
            shift
            ;;
        --chaos)
            RUN_CHAOS=true
            shift
            ;;
        --security)
            RUN_SECURITY=true
            shift
            ;;
        --no-build)
            RUN_BUILD=false
            shift
            ;;
        --skip-cleanup)
            SKIP_CLEANUP=true
            shift
            ;;
        --kind-image)
            KIND_NODE_IMAGE="$2"
            shift 2
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Check dependencies
check_dependencies() {
    log_section "Checking Dependencies"
    
    local missing_deps=()
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        missing_deps+=("python3")
    fi
    
    # Check pip
    if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
        missing_deps+=("pip")
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        missing_deps+=("docker")
    fi
    
    # Check Kind (install if missing)
    if ! command -v kind &> /dev/null; then
        log_info "Installing Kind ${KIND_VERSION}..."
        curl -Lo ./kind "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-amd64"
        chmod +x ./kind
        sudo mv ./kind /usr/local/bin/kind
        log_success "Kind installed"
    fi
    
    # Check kubectl (install if missing)
    if ! command -v kubectl &> /dev/null; then
        log_info "Installing kubectl ${KUBECTL_VERSION}..."
        curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"
        chmod +x kubectl
        sudo mv kubectl /usr/local/bin/
        log_success "kubectl installed"
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        log_error "Missing dependencies: ${missing_deps[*]}"
        log_error "Please install missing dependencies and try again"
        exit 1
    fi
    
    log_success "All dependencies available"
}

# Setup Python environment
setup_python_env() {
    log_section "Setting up Python Environment"
    
    cd consistent_hashing
    
    # Create virtual environment if it doesn't exist
    if [ ! -d ".venv" ]; then
        log_info "Creating Python virtual environment..."
        python3 -m venv .venv
    fi
    
    # Activate virtual environment
    source .venv/bin/activate
    
    # Upgrade pip
    log_info "Upgrading pip..."
    python -m pip install --upgrade pip
    
    # Install dependencies
    log_info "Installing project dependencies..."
    pip install -r requirements.txt
    
    if [ -f "tests/requirements-test.txt" ]; then
        log_info "Installing test dependencies..."
        pip install -r tests/requirements-test.txt
    fi
    
    # Set PYTHONPATH
    export PYTHONPATH="${PWD}"
    
    cd ..
    log_success "Python environment ready"
}

# Run unit tests
run_unit_tests() {
    log_section "Running Unit Tests"
    
    cd consistent_hashing
    source .venv/bin/activate
    
    log_info "Executing unit tests with coverage..."
    python -m pytest tests/unit/ -v \
        --cov=gateway \
        --cov=storage \
        --cov-report=xml \
        --cov-report=html \
        --junit-xml=test-results-unit.xml
    
    log_success "Unit tests completed"
    
    # Show coverage summary
    if [ -f "htmlcov/index.html" ]; then
        log_info "Coverage report generated: consistent_hashing/htmlcov/index.html"
    fi
    
    cd ..
}

# Setup Kind cluster
setup_kind_cluster() {
    log_section "Setting up Kind Cluster"
    
    # Handle K3s conflict by unsetting KUBECONFIG if it points to K3s
    if [[ "${KUBECONFIG:-}" == *"k3s"* ]]; then
        log_warning "Detected K3s KUBECONFIG conflict. Temporarily unsetting KUBECONFIG for Kind..."
        export K3S_KUBECONFIG_BACKUP="$KUBECONFIG"
        unset KUBECONFIG
    fi
    
    # Install PyYAML if needed for robust setup
    if ! python3 -c "import yaml" 2>/dev/null; then
        log_info "Installing PyYAML for robust Kind setup..."
        pip install pyyaml
    fi
    
    # Use the robust Kind cluster setup
    log_info "Creating Kind cluster with robust setup (retry logic + fallback configurations)..."
    if python3 consistent_hashing/setup-kind-robust.py \
        --cluster-name "${KIND_CLUSTER_NAME}" \
        --node-image "${KIND_NODE_IMAGE}" \
        --create; then
        log_success "Kind cluster ready"
    else
        log_error "Robust Kind setup failed. Cleaning up and trying original method as fallback..."
        
        # Clean up any partial cluster before fallback
        log_info "Cleaning up partial cluster..."
        kind delete cluster --name "${KIND_CLUSTER_NAME}" 2>/dev/null || true
        
        # Fallback to original method (single node for reliability)
        log_info "Creating single-node Kind cluster with image: ${KIND_NODE_IMAGE}..."
        cat <<EOF | kind create cluster --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: ${KIND_CLUSTER_NAME}
nodes:
- role: control-plane
  image: ${KIND_NODE_IMAGE}
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
        eviction-hard: "memory.available<100Mi,nodefs.available<1Gi"
  extraPortMappings:
  - containerPort: 30000
    hostPort: 30000
    protocol: TCP
  - containerPort: 32000
    hostPort: 32000
    protocol: TCP
EOF
        
        # Wait for cluster to be ready
        log_info "Waiting for cluster to be ready..."
        kubectl cluster-info --context "kind-${KIND_CLUSTER_NAME}"
        kubectl wait --for=condition=Ready nodes --all --timeout=300s
        
        log_success "Kind cluster ready (fallback method)"
    fi
}

# Build and load Docker images
build_and_load_images() {
    log_section "Building and Loading Docker Images"
    
    cd consistent_hashing
    
    # Build gateway image
    log_info "Building gateway image..."
    docker build -f gateway/Dockerfile -t consistent-hashing/gateway:test .
    
    # Build kvstore image
    log_info "Building kvstore image..."
    docker build -f storage/kvstore/Dockerfile -t consistent-hashing/kvstore:test .
    
    # Load images into Kind cluster
    log_info "Loading images into Kind cluster..."
    kind load docker-image consistent-hashing/gateway:test --name "${KIND_CLUSTER_NAME}"
    kind load docker-image consistent-hashing/kvstore:test --name "${KIND_CLUSTER_NAME}"
    
    cd ..
    log_success "Docker images built and loaded"
}

# Deploy system to Kind cluster
deploy_system() {
    log_section "Deploying System to Kind Cluster"
    
    cd consistent_hashing
    
    # Create namespace
    log_info "Creating namespace..."
    kubectl create namespace "${NAMESPACE}" || true
    
    # Apply namespace
    kubectl apply -f k8s/namespace.yaml || true
    
    # Deploy gateway
    log_info "Deploying gateway..."
    sed 's|image: consistent-hashing/gateway:latest|image: consistent-hashing/gateway:test|g' k8s/gateway-deployment.yaml | \
    sed 's|imagePullPolicy: Never|imagePullPolicy: IfNotPresent|g' | \
    kubectl apply -f -
    
    # Deploy kvstore
    log_info "Deploying kvstore..."
    sed 's|image: consistent-hashing/kvstore:latest|image: consistent-hashing/kvstore:test|g' k8s/kvstore-deployment.yaml | \
    sed 's|imagePullPolicy: Never|imagePullPolicy: IfNotPresent|g' | \
    kubectl apply -f -
    
    cd ..
    log_success "System deployed"
}

# Wait for services to be ready
wait_for_services() {
    log_section "Waiting for Services to be Ready"
    
    # Check initial pod status
    kubectl get pods -n "${NAMESPACE}" -o wide
    
    # Wait for gateway pods
    log_info "Waiting for gateway pods..."
    if ! kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=gateway -n "${NAMESPACE}" --timeout=600s; then
        log_error "Gateway pods failed to become ready"
        kubectl get pods -n "${NAMESPACE}"
        kubectl describe pods -l app.kubernetes.io/name=gateway -n "${NAMESPACE}"
        kubectl logs -l app.kubernetes.io/name=gateway -n "${NAMESPACE}" --tail=100 || true
        exit 1
    fi
    
    # Wait for kvstore pods
    log_info "Waiting for kvstore pods..."
    if ! kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=kvstore -n "${NAMESPACE}" --timeout=600s; then
        log_error "KVStore pods failed to become ready"
        kubectl get pods -n "${NAMESPACE}"
        kubectl describe pods -l app.kubernetes.io/name=kvstore -n "${NAMESPACE}"
        kubectl logs -l app.kubernetes.io/name=kvstore -n "${NAMESPACE}" --tail=100 || true
        exit 1
    fi
    
    # Check final pod status
    kubectl get pods -n "${NAMESPACE}" -o wide
    log_success "All services ready"
}

# Setup port forwarding
setup_port_forwarding() {
    log_section "Setting up Port Forwarding"
    
    # Port forward gateway service
    log_info "Setting up gateway port forwarding..."
    kubectl port-forward svc/gateway-service 8000:8000 -n "${NAMESPACE}" &
    GATEWAY_PF_PID=$!
    
    # Port forward kvstore service  
    log_info "Setting up kvstore port forwarding..."
    kubectl port-forward svc/kvstore-service 8080:8080 -n "${NAMESPACE}" &
    KVSTORE_PF_PID=$!
    
    # Wait for port forwards to be ready
    log_info "Waiting for port forwards to be ready..."
    sleep 10
    
    # Test connectivity
    if curl -f http://localhost:8000/nodes; then
        log_success "Port forwarding ready"
    else
        log_error "Gateway not accessible"
        exit 1
    fi
    
    # Give additional time for KV stores to register with gateway
    log_info "Allowing time for KV stores to register with gateway..."
    sleep 15
}

# Run integration tests
run_integration_tests() {
    log_section "Running Integration Tests"
    
    cd consistent_hashing
    source .venv/bin/activate
    
    # Test system health
    log_info "Checking system health..."
    python run_tests.py --check-system
    
    # Run integration tests
    log_info "Running e2e tests..."
    python -m pytest tests/e2e/ -v \
        --junit-xml=test-results-integration.xml \
        -m "e2e" \
        --timeout=300
    
    cd ..
    log_success "Integration tests completed"
}

# Run system validation tests
run_system_validation() {
    log_section "Running System Validation Tests"
    
    cd consistent_hashing
    source .venv/bin/activate
    
    log_info "Running basic operations validation..."
    if python -m tests.system_validation --basic-ops; then
        log_success "System validation passed"
    else
        log_error "System validation failed"
        exit 1
    fi
    
    cd ..
}

# Run load tests
run_load_tests() {
    log_section "Running Load Tests"
    
    cd consistent_hashing
    source .venv/bin/activate
    
    log_info "Running load test..."
    if python -m tests.system_validation --load-test; then
        log_success "Load tests completed"
    else
        log_error "Load tests failed"
        exit 1
    fi
    
    cd ..
}

# Collect system information
collect_system_info() {
    log_section "Collecting System Information"
    
    echo "=== Cluster Information ==="
    kubectl get nodes -o wide
    
    echo "=== Pod Status ==="
    kubectl get pods -A -o wide
    
    echo "=== Service Status ==="
    kubectl get svc -A
    
    echo "=== Gateway Logs ==="
    kubectl logs -l app.kubernetes.io/name=gateway -n "${NAMESPACE}" --tail=50 || true
    
    echo "=== KVStore Logs ==="
    kubectl logs -l app.kubernetes.io/name=kvstore -n "${NAMESPACE}" --tail=50 || true
}

# Run chaos tests
run_chaos_tests() {
    log_section "Running Chaos Engineering Tests"
    
    cd consistent_hashing
    source .venv/bin/activate
    
    log_info "Running chaos tests (limited set for local execution)..."
    python -m pytest tests/chaos/ -v \
        --junit-xml=test-results-chaos.xml \
        -m "chaos" \
        --timeout=600 \
        -k "not memory_pressure and not high_connection_load" || log_warning "Some chaos tests may have failed"
    
    cd ..
    log_success "Chaos tests completed"
}

# Run security scan
run_security_scan() {
    log_section "Running Security Scan"
    
    if ! command -v trivy &> /dev/null; then
        log_warning "Trivy not installed. Installing..."
        # Install trivy
        sudo apt-get update
        sudo apt-get install wget apt-transport-https gnupg lsb-release
        wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo apt-key add -
        echo "deb https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee -a /etc/apt/sources.list.d/trivy.list
        sudo apt-get update
        sudo apt-get install trivy
    fi
    
    log_info "Running Trivy security scan..."
    trivy fs --format table ./consistent_hashing/
    
    log_success "Security scan completed"
}

# Run build validation
run_build_validation() {
    log_section "Running Build Validation"
    
    cd consistent_hashing
    
    # Build gateway image
    log_info "Building gateway image for validation..."
    docker build -f gateway/Dockerfile -t consistent-hashing/gateway:build-test .
    
    # Build kvstore image
    log_info "Building kvstore image for validation..."
    docker build -f storage/kvstore/Dockerfile -t consistent-hashing/kvstore:build-test .
    
    # Test image functionality
    log_info "Testing image functionality..."
    docker run --rm consistent-hashing/gateway:build-test python -c "from simple_hash_ring import SimpleHashRing; print('Gateway image OK')"
    docker run --rm consistent-hashing/kvstore:build-test python -c "import kvstore_service; print('KVStore image OK')"
    
    cd ..
    log_success "Build validation completed"
}

# Cleanup
cleanup() {
    log_section "Cleanup"
    
    # Kill port forwards
    if [ ! -z "${GATEWAY_PF_PID:-}" ]; then
        log_info "Stopping gateway port forward..."
        kill $GATEWAY_PF_PID || true
    fi
    if [ ! -z "${KVSTORE_PF_PID:-}" ]; then
        log_info "Stopping kvstore port forward..."
        kill $KVSTORE_PF_PID || true
    fi
    
    # Restore K3s KUBECONFIG if it was backed up
    if [ ! -z "${K3S_KUBECONFIG_BACKUP:-}" ]; then
        log_info "Restoring K3s KUBECONFIG..."
        export KUBECONFIG="$K3S_KUBECONFIG_BACKUP"
        unset K3S_KUBECONFIG_BACKUP
    fi
    
    # Cleanup Kind cluster
    if [ "$SKIP_CLEANUP" = false ]; then
        # Handle K3s conflict during cleanup too
        if [[ "${KUBECONFIG:-}" == *"k3s"* ]] && [ -z "${K3S_KUBECONFIG_BACKUP:-}" ]; then
            log_warning "Detected K3s KUBECONFIG during cleanup. Temporarily unsetting for Kind cleanup..."
            local TEMP_K3S_BACKUP="$KUBECONFIG"
            unset KUBECONFIG
            log_info "Deleting Kind cluster..."
            kind delete cluster --name "${KIND_CLUSTER_NAME}" || true
            export KUBECONFIG="$TEMP_K3S_BACKUP"
        else
            log_info "Deleting Kind cluster..."
            kind delete cluster --name "${KIND_CLUSTER_NAME}" || true
        fi
    else
        log_warning "Skipping Kind cluster cleanup (--skip-cleanup flag used)"
        log_info "To manually cleanup: kind delete cluster --name ${KIND_CLUSTER_NAME}"
    fi
}

# Main execution
main() {
    log_section "Local Workflow Test Runner Started"
    log_info "Configuration:"
    log_info "  Unit Tests: $RUN_UNIT"
    log_info "  Integration Tests: $RUN_INTEGRATION" 
    log_info "  Chaos Tests: $RUN_CHAOS"
    log_info "  Security Scan: $RUN_SECURITY"
    log_info "  Build Validation: $RUN_BUILD"
    log_info "  Kind Node Image: $KIND_NODE_IMAGE"
    log_info "  Skip Cleanup: $SKIP_CLEANUP"
    
    # Set trap for cleanup
    trap cleanup EXIT
    
    # Check dependencies
    check_dependencies
    
    # Setup Python environment
    setup_python_env
    
    # Run unit tests
    if [ "$RUN_UNIT" = true ]; then
        run_unit_tests
    fi
    
    # Run build validation
    if [ "$RUN_BUILD" = true ]; then
        run_build_validation
    fi
    
    # Run integration tests
    if [ "$RUN_INTEGRATION" = true ]; then
        setup_kind_cluster
        build_and_load_images
        deploy_system
        wait_for_services
        setup_port_forwarding
        run_integration_tests
        run_system_validation
        run_load_tests
        collect_system_info
    fi
    
    # Run chaos tests
    if [ "$RUN_CHAOS" = true ]; then
        run_chaos_tests
    fi
    
    # Run security scan
    if [ "$RUN_SECURITY" = true ]; then
        run_security_scan
    fi
    
    log_section "All Tests Completed Successfully!"
    log_success "Local workflow execution finished"
    
    if [ "$RUN_INTEGRATION" = true ]; then
        log_info "Integration test results: consistent_hashing/test-results-integration.xml"
    fi
    if [ "$RUN_UNIT" = true ]; then
        log_info "Unit test results: consistent_hashing/test-results-unit.xml"
        log_info "Coverage report: consistent_hashing/htmlcov/index.html"
    fi
}

# Run main function
main "$@" 