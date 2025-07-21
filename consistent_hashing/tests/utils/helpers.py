"""
Test helper utilities and common functions
"""

import time
import requests
import random
import string
import json
from typing import Dict, List, Any, Optional
from collections import defaultdict


def wait_for_service(url: str, timeout: int = 30, interval: float = 0.5) -> bool:
    """
    Wait for a service to become available
    
    Args:
        url: Service URL to check
        timeout: Maximum time to wait in seconds
        interval: Check interval in seconds
        
    Returns:
        True if service becomes available, False if timeout
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(interval)
    return False


def wait_for_node_registration(gateway_url: str, expected_count: int, timeout: int = 30) -> bool:
    """
    Wait for expected number of nodes to register with gateway
    
    Args:
        gateway_url: Gateway base URL
        expected_count: Expected number of nodes
        timeout: Maximum time to wait
        
    Returns:
        True if expected nodes are registered, False if timeout
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{gateway_url}/nodes")
            if response.status_code == 200:
                nodes = response.json()["nodes"]
                if len(nodes) >= expected_count:
                    return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def generate_random_string(length: int = 10) -> str:
    """Generate a random string of specified length"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def generate_test_data(count: int = 100) -> Dict[str, Any]:
    """
    Generate test data for load testing
    
    Args:
        count: Number of key-value pairs to generate
        
    Returns:
        Dictionary of test data
    """
    data = {}
    for i in range(count):
        key = f"test_key_{i}_{generate_random_string(5)}"
        value = {
            "id": i,
            "name": f"test_name_{i}",
            "data": generate_random_string(50),
            "timestamp": time.time(),
            "metadata": {
                "type": "test",
                "version": "1.0",
                "tags": [f"tag_{j}" for j in range(random.randint(1, 5))]
            }
        }
        data[key] = value
    return data


def store_test_data(gateway_url: str, test_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Store test data in the consistent hashing system
    
    Args:
        gateway_url: Gateway base URL
        test_data: Dictionary of key-value pairs to store
        
    Returns:
        Dictionary mapping keys to the nodes they were stored on
    """
    key_to_node = {}
    
    for key, value in test_data.items():
        try:
            # Get node for key
            response = requests.get(f"{gateway_url}/nodes/{key}")
            if response.status_code == 200:
                node_data = response.json()
                node_id = node_data["node_id"]
                kvstore_port = node_data["port"]
                
                # Store data
                response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                    json={"key": key, "value": value}
                )
                
                if response.status_code == 200:
                    key_to_node[key] = node_id
                    
        except requests.RequestException as e:
            print(f"Failed to store key {key}: {e}")
    
    return key_to_node


def verify_test_data(gateway_url: str, test_data: Dict[str, Any], key_to_node: Dict[str, str]) -> Dict[str, bool]:
    """
    Verify that stored test data can be retrieved correctly
    
    Args:
        gateway_url: Gateway base URL
        test_data: Original test data
        key_to_node: Mapping of keys to nodes (for verification)
        
    Returns:
        Dictionary mapping keys to verification status
    """
    verification_results = {}
    
    for key, expected_value in test_data.items():
        try:
            # Get node for key
            response = requests.get(f"{gateway_url}/nodes/{key}")
            if response.status_code == 200:
                node_data = response.json()
                kvstore_port = node_data["port"]
                
                # Retrieve data
                response = requests.get(f"http://127.0.0.1:{kvstore_port}/get/{key}")
                if response.status_code == 200:
                    retrieved_value = response.json()["value"]
                    verification_results[key] = (retrieved_value == expected_value)
                else:
                    verification_results[key] = False
            else:
                verification_results[key] = False
                
        except requests.RequestException:
            verification_results[key] = False
    
    return verification_results


def analyze_key_distribution(gateway_url: str, keys: List[str]) -> Dict[str, Any]:
    """
    Analyze how keys are distributed across nodes
    
    Args:
        gateway_url: Gateway base URL
        keys: List of keys to analyze
        
    Returns:
        Distribution analysis results
    """
    node_distribution = defaultdict(list)
    node_counts = defaultdict(int)
    
    for key in keys:
        try:
            response = requests.get(f"{gateway_url}/nodes/{key}")
            if response.status_code == 200:
                node_data = response.json()
                node_id = node_data["node_id"]
                
                node_distribution[node_id].append(key)
                node_counts[node_id] += 1
                
        except requests.RequestException:
            continue
    
    # Calculate statistics
    counts = list(node_counts.values())
    if counts:
        min_count = min(counts)
        max_count = max(counts)
        avg_count = sum(counts) / len(counts)
        std_dev = (sum((x - avg_count) ** 2 for x in counts) / len(counts)) ** 0.5
        
        return {
            "node_distribution": dict(node_distribution),
            "node_counts": dict(node_counts),
            "statistics": {
                "min_keys_per_node": min_count,
                "max_keys_per_node": max_count,
                "avg_keys_per_node": avg_count,
                "std_deviation": std_dev,
                "load_balance_ratio": min_count / max_count if max_count > 0 else 0
            }
        }
    else:
        return {
            "node_distribution": {},
            "node_counts": {},
            "statistics": {}
        }


def measure_operation_latency(operation_func, *args, **kwargs) -> Dict[str, float]:
    """
    Measure the latency of an operation
    
    Args:
        operation_func: Function to measure
        *args, **kwargs: Arguments for the function
        
    Returns:
        Latency measurements
    """
    start_time = time.time()
    
    try:
        result = operation_func(*args, **kwargs)
        end_time = time.time()
        
        return {
            "latency_ms": (end_time - start_time) * 1000,
            "success": True,
            "result": result
        }
    except Exception as e:
        end_time = time.time()
        
        return {
            "latency_ms": (end_time - start_time) * 1000,
            "success": False,
            "error": str(e)
        }


def run_load_test(gateway_url: str, num_operations: int = 100, num_threads: int = 10) -> Dict[str, Any]:
    """
    Run a load test against the system
    
    Args:
        gateway_url: Gateway base URL
        num_operations: Total number of operations to perform
        num_threads: Number of concurrent threads
        
    Returns:
        Load test results
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    results = {
        "total_operations": num_operations,
        "successful_operations": 0,
        "failed_operations": 0,
        "latencies": [],
        "errors": []
    }
    
    def perform_operation(operation_id):
        """Perform a single operation"""
        try:
            key = f"load_test_key_{operation_id}_{generate_random_string(5)}"
            value = f"load_test_value_{operation_id}"
            
            # Get node for key
            start_time = time.time()
            response = requests.get(f"{gateway_url}/nodes/{key}", timeout=5)
            
            if response.status_code == 200:
                node_data = response.json()
                kvstore_port = node_data["port"]
                
                # Store data
                response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                    json={"key": key, "value": value},
                    timeout=5
                )
                
                if response.status_code == 200:
                    # Retrieve data to verify
                    response = requests.get(f"http://127.0.0.1:{kvstore_port}/get/{key}", timeout=5)
                    
                    end_time = time.time()
                    latency = (end_time - start_time) * 1000
                    
                    if response.status_code == 200 and response.json()["value"] == value:
                        return {"success": True, "latency": latency}
                    else:
                        return {"success": False, "latency": latency, "error": "Verification failed"}
                else:
                    end_time = time.time()
                    return {"success": False, "latency": (end_time - start_time) * 1000, "error": "Store failed"}
            else:
                end_time = time.time()
                return {"success": False, "latency": (end_time - start_time) * 1000, "error": "Node lookup failed"}
                
        except Exception as e:
            end_time = time.time()
            return {"success": False, "latency": (end_time - start_time) * 1000, "error": str(e)}
    
    # Run operations concurrently
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        future_to_id = {executor.submit(perform_operation, i): i for i in range(num_operations)}
        
        for future in as_completed(future_to_id):
            result = future.result()
            
            if result["success"]:
                results["successful_operations"] += 1
                results["latencies"].append(result["latency"])
            else:
                results["failed_operations"] += 1
                results["errors"].append(result.get("error", "Unknown error"))
    
    # Calculate latency statistics
    if results["latencies"]:
        latencies = sorted(results["latencies"])
        results["latency_stats"] = {
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "avg_ms": sum(latencies) / len(latencies),
            "p50_ms": latencies[len(latencies) // 2],
            "p95_ms": latencies[int(len(latencies) * 0.95)],
            "p99_ms": latencies[int(len(latencies) * 0.99)]
        }
    
    return results


def check_system_health(gateway_url: str, kvstore_ports: List[int]) -> Dict[str, Any]:
    """
    Check the health of the entire system
    
    Args:
        gateway_url: Gateway base URL
        kvstore_ports: List of KV store ports
        
    Returns:
        System health status
    """
    health_status = {
        "gateway_health": False,
        "kvstore_health": {},
        "registered_nodes": 0,
        "overall_healthy": False
    }
    
    # Check gateway health
    try:
        response = requests.get(f"{gateway_url}/health", timeout=5)
        health_status["gateway_health"] = response.status_code == 200
    except requests.RequestException:
        health_status["gateway_health"] = False
    
    # Check KV store health
    for port in kvstore_ports:
        try:
            response = requests.get(f"http://127.0.0.1:{port}/health", timeout=5)
            health_status["kvstore_health"][port] = response.status_code == 200
        except requests.RequestException:
            health_status["kvstore_health"][port] = False
    
    # Check registered nodes
    try:
        response = requests.get(f"{gateway_url}/nodes", timeout=5)
        if response.status_code == 200:
            nodes = response.json()["nodes"]
            health_status["registered_nodes"] = len(nodes)
    except requests.RequestException:
        pass
    
    # Determine overall health
    gateway_ok = health_status["gateway_health"]
    kvstores_ok = any(health_status["kvstore_health"].values())
    nodes_registered = health_status["registered_nodes"] > 0
    
    health_status["overall_healthy"] = gateway_ok and kvstores_ok and nodes_registered
    
    return health_status


class ConsistentHashingTestClient:
    """Test client for interacting with the consistent hashing system"""
    
    def __init__(self, gateway_url: str):
        self.gateway_url = gateway_url
        self.session = requests.Session()
    
    def get_node_for_key(self, key: str) -> Optional[Dict[str, Any]]:
        """Get the node responsible for a key"""
        try:
            response = self.session.get(f"{self.gateway_url}/nodes/{key}")
            if response.status_code == 200:
                return response.json()
        except requests.RequestException:
            pass
        return None
    
    def store_key(self, key: str, value: Any) -> bool:
        """Store a key-value pair"""
        node_data = self.get_node_for_key(key)
        if node_data:
            try:
                kvstore_port = node_data["port"]
                response = self.session.post(f"http://127.0.0.1:{kvstore_port}/put",
                    json={"key": key, "value": value}
                )
                return response.status_code == 200
            except requests.RequestException:
                pass
        return False
    
    def retrieve_key(self, key: str) -> Optional[Any]:
        """Retrieve a value by key"""
        node_data = self.get_node_for_key(key)
        if node_data:
            try:
                kvstore_port = node_data["port"]
                response = self.session.get(f"http://127.0.0.1:{kvstore_port}/get/{key}")
                if response.status_code == 200:
                    return response.json()["value"]
            except requests.RequestException:
                pass
        return None
    
    def delete_key(self, key: str) -> bool:
        """Delete a key"""
        node_data = self.get_node_for_key(key)
        if node_data:
            try:
                kvstore_port = node_data["port"]
                response = self.session.delete(f"http://127.0.0.1:{kvstore_port}/delete/{key}")
                return response.status_code == 200
            except requests.RequestException:
                pass
        return False
    
    def get_all_nodes(self) -> Optional[Dict[str, Any]]:
        """Get information about all nodes"""
        try:
            response = self.session.get(f"{self.gateway_url}/nodes")
            if response.status_code == 200:
                return response.json()["nodes"]
        except requests.RequestException:
            pass
        return None 