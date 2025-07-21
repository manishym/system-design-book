"""
Pytest configuration and shared fixtures for consistent hashing tests
"""

import pytest
import time
import threading
import requests
import subprocess
import socket
from typing import Dict, List, Any, Optional
import tempfile
import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from gateway.simple_hash_ring import SimpleHashRing
from gateway.gateway_service_simple import SimpleGatewayService, NodeInfo
from storage.kvstore.kvstore_service import KVStoreService


def find_free_port() -> int:
    """Find a free port on localhost"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture
def hash_ring():
    """Create a fresh hash ring for testing"""
    return SimpleHashRing(virtual_nodes=10)  # Smaller for faster tests


@pytest.fixture
def sample_nodes():
    """Sample node data for testing"""
    return [
        {"node_id": "node1", "address": "127.0.0.1", "port": 8081},
        {"node_id": "node2", "address": "127.0.0.1", "port": 8082},
        {"node_id": "node3", "address": "127.0.0.1", "port": 8083},
    ]


@pytest.fixture
def gateway_service():
    """Create a gateway service for testing"""
    port = find_free_port()
    service = SimpleGatewayService(
        gateway_id=f"gateway-test-{port}",
        listen_port=port,
        peer_gateways=[]
    )
    
    yield service
    
    # Cleanup
    if hasattr(service, 'running') and service.running:
        service.stop()


@pytest.fixture
def kvstore_service():
    """Create a KV store service for testing"""
    port = find_free_port()
    gateway_port = find_free_port()
    
    service = KVStoreService(
        node_id=f"kvstore-test-{port}",
        listen_port=port,
        gateway_address=f"127.0.0.1:{gateway_port}"
    )
    
    yield service
    
    # Cleanup
    if service.running:
        service.stop()


@pytest.fixture
def test_keys():
    """Common test keys for consistent distribution testing"""
    return [
        "user:123", "user:456", "user:789",
        "product:abc", "product:def", "product:ghi",
        "order:001", "order:002", "order:003",
        "session:aaa", "session:bbb", "session:ccc"
    ]


@pytest.fixture(scope="session")
def kubernetes_config():
    """Kubernetes configuration for e2e tests"""
    return {
        "namespace": "consistent-hashing-test",
        "gateway_service": "gateway-service",
        "kvstore_service": "kvstore-service",
        "kubeconfig": os.environ.get("KUBECONFIG", "/etc/rancher/k3s/k3s.yaml")
    }


class TestServiceManager:
    """Helper class to manage test services"""
    
    def __init__(self):
        self.services: List[Any] = []
        self.threads: List[threading.Thread] = []
        
    def start_gateway(self, gateway_id: Optional[str] = None, port: Optional[int] = None, peer_gateways: Optional[List[str]] = None, clear_nodes: bool = True) -> SimpleGatewayService:
        """Start a gateway service"""
        if port is None:
            port = find_free_port()
        if gateway_id is None:
            gateway_id = f"gateway-{port}"
        if peer_gateways is None:
            peer_gateways = []
            
        service = SimpleGatewayService(gateway_id, port, peer_gateways)
        
        # Start in background thread
        thread = threading.Thread(target=service.start, daemon=True)
        thread.start()
        
        # Wait for service to be ready
        self._wait_for_service(f"http://127.0.0.1:{port}/health", timeout=10)
        
        # Clear any existing nodes for clean test isolation
        if clear_nodes:
            try:
                response = requests.post(f"http://127.0.0.1:{port}/admin/clear_nodes", timeout=5)
                if response.status_code == 200:
                    cleared = response.json().get('cleared_nodes', 0)
                    if cleared > 0:
                        print(f"Cleared {cleared} existing nodes from gateway for clean test state")
            except requests.RequestException:
                pass  # Ignore if endpoint not available
        
        self.services.append(service)
        self.threads.append(thread)
        
        return service
        
    def start_kvstore(self, node_id: Optional[str] = None, port: Optional[int] = None, gateway_address: Optional[str] = None) -> KVStoreService:
        """Start a KV store service"""
        if port is None:
            port = find_free_port()
        if node_id is None:
            node_id = f"kvstore-{port}"
        if gateway_address is None:
            gateway_address = "127.0.0.1:8000"  # Default gateway
            
        service = KVStoreService(node_id, port, gateway_address)
        
        # Start in background thread
        thread = threading.Thread(target=service.start, daemon=True)
        thread.start()
        
        # Wait for service to be ready
        self._wait_for_service(f"http://127.0.0.1:{port}/health", timeout=10)
        
        self.services.append(service)
        self.threads.append(thread)
        
        return service
        
    def _wait_for_service(self, url: str, timeout: int = 10):
        """Wait for a service to become available"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, timeout=1)
                if response.status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(0.1)
        raise TimeoutError(f"Service at {url} did not become available within {timeout} seconds")
        
    def stop_all(self):
        """Stop all managed services"""
        for service in self.services:
            if hasattr(service, 'stop'):
                service.stop()
        
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=2)
                
        self.services.clear()
        self.threads.clear()


@pytest.fixture
def service_manager():
    """Service manager fixture for integration tests"""
    manager = TestServiceManager()
    yield manager
    manager.stop_all()


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


# Pytest configuration
def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as an end-to-end test"
    )
    config.addinivalue_line(
        "markers", "chaos: mark test as a chaos engineering test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Add markers to tests based on their location"""
    for item in items:
        # Add unit marker to unit tests
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        
        # Add integration marker to integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            
        # Add e2e marker to e2e tests
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
            item.add_marker(pytest.mark.slow)
            
        # Add chaos marker to chaos tests
        if "chaos" in str(item.fspath):
            item.add_marker(pytest.mark.chaos)
            item.add_marker(pytest.mark.slow) 