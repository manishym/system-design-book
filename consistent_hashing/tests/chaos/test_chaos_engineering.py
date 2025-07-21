"""
Chaos engineering tests for the consistent hashing system

These tests introduce various failures and verify system resilience.
"""

import pytest
import time
import requests
import threading
import random
import signal
import os
from collections import defaultdict
from unittest.mock import patch


@pytest.mark.chaos
class TestNodeFailures:
    """Test various node failure scenarios"""
    
    def test_random_node_failures(self, service_manager):
        """Test system resilience to random node failures"""
        # Start a larger system
        gateway = service_manager.start_gateway("gateway1", 8000)
        
        kvstores = []
        for i in range(6):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                8080 + i,
                "127.0.0.1:8000"
            )
            kvstores.append(kvstore)
        
        time.sleep(3)
        
        # Store initial data
        initial_keys = [f"chaos_key_{i}" for i in range(100)]
        stored_data = {}
        
        for key in initial_keys:
            # Get node for key
            response = requests.get(f"http://127.0.0.1:8000/nodes/{key}")
            if response.status_code == 200:
                node_data = response.json()
                kvstore_port = node_data["port"]
                
                # Store data
                response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                    json={"key": key, "value": f"value_{key}"}
                )
                if response.status_code == 200:
                    stored_data[key] = node_data["node_id"]
        
        print(f"Initially stored {len(stored_data)} keys")
        
        # Randomly fail nodes
        failed_nodes = []
        for _ in range(3):  # Fail 3 out of 6 nodes
            if kvstores:
                failed_kvstore = random.choice(kvstores)
                kvstores.remove(failed_kvstore)
                
                # Stop the node
                failed_kvstore.stop()
                failed_nodes.append(failed_kvstore.node_id)
                
                # Wait a bit between failures
                time.sleep(2)
        
        print(f"Failed nodes: {failed_nodes}")
        
        # Wait for failure detection
        time.sleep(40)
        
        # Try to retrieve data - some might be lost, but system should not crash
        retrievable_count = 0
        for key in stored_data:
            try:
                # Get current node for key (might be remapped)
                response = requests.get(f"http://127.0.0.1:8000/nodes/{key}")
                if response.status_code == 200:
                    node_data = response.json()
                    kvstore_port = node_data["port"]
                    
                    # Try to retrieve
                    response = requests.get(f"http://127.0.0.1:{kvstore_port}/get/{key}")
                    if response.status_code == 200:
                        retrievable_count += 1
                    
            except Exception as e:
                print(f"Error retrieving {key}: {e}")
        
        # System should remain operational
        response = requests.get("http://127.0.0.1:8000/health")
        assert response.status_code == 200
        
        # Should be able to store new data
        new_key = "chaos_recovery_test"
        response = requests.get(f"http://127.0.0.1:8000/nodes/{new_key}")
        if response.status_code == 200:
            node_data = response.json()
            kvstore_port = node_data["port"]
            
            response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                json={"key": new_key, "value": "recovery_value"}
            )
            assert response.status_code == 200
    
    def test_cascading_failures(self, service_manager):
        """Test system behavior during cascading failures"""
        # Start system
        gateway = service_manager.start_gateway("gateway1", 8000)
        
        kvstores = []
        for i in range(4):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                8080 + i,
                "127.0.0.1:8000"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Store data
        test_keys = [f"cascade_key_{i}" for i in range(50)]
        for key in test_keys:
            response = requests.get(f"http://127.0.0.1:8000/nodes/{key}")
            if response.status_code == 200:
                node_data = response.json()
                kvstore_port = node_data["port"]
                
                requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                    json={"key": key, "value": f"value_{key}"}
                )
        
        # Simulate cascading failures - fail nodes one by one quickly
        for i in range(3):
            if kvstores:
                kvstore = kvstores.pop(0)
                kvstore.stop()
                time.sleep(1)  # Very short interval between failures
        
        # System should still respond
        time.sleep(5)
        response = requests.get("http://127.0.0.1:8000/health")
        assert response.status_code == 200
        
        # Should still be able to get node assignments
        response = requests.get("http://127.0.0.1:8000/nodes/test_key")
        # Should either work or return 404, but not crash
        assert response.status_code in [200, 404]
    
    def test_node_recovery_after_failure(self, service_manager):
        """Test node recovery and rejoining the cluster"""
        # Start system
        gateway = service_manager.start_gateway("gateway1", 8000)
        
        kvstores = []
        for i in range(3):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                8080 + i,
                "127.0.0.1:8000"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Verify initial state
        response = requests.get("http://127.0.0.1:8000/nodes")
        assert response.status_code == 200
        initial_nodes = set(response.json()["nodes"].keys())
        assert len(initial_nodes) == 3
        
        # Stop one node
        failed_kvstore = kvstores[1]
        failed_node_id = failed_kvstore.node_id
        failed_kvstore.stop()
        
        # Wait for failure detection
        time.sleep(35)
        
        # Start a new node with same ID (simulating recovery)
        recovered_kvstore = service_manager.start_kvstore(
            failed_node_id,
            8081,  # Same port
            "127.0.0.1:8000"
        )
        
        # Wait for recovery
        time.sleep(3)
        
        # Verify node is back
        response = requests.get("http://127.0.0.1:8000/nodes")
        assert response.status_code == 200
        current_nodes = response.json()["nodes"]
        
        # Recovered node should be active
        if failed_node_id in current_nodes:
            assert current_nodes[failed_node_id]["status"] == "active"


@pytest.mark.chaos
class TestNetworkPartitions:
    """Test network partition scenarios"""
    
    def test_gateway_isolation(self, service_manager):
        """Test behavior when gateway becomes isolated"""
        # Start system
        gateway = service_manager.start_gateway("gateway1", 8000)
        
        kvstores = []
        for i in range(3):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                8080 + i,
                "127.0.0.1:8000"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Simulate network partition by blocking requests to gateway
        with patch('requests.post') as mock_post:
            # Make heartbeats fail
            mock_post.side_effect = requests.ConnectionError("Network partition")
            
            # Wait for several heartbeat cycles
            time.sleep(20)
            
            # Gateway should still respond to local requests
            response = requests.get("http://127.0.0.1:8000/health")
            assert response.status_code == 200
            
            # But nodes might be marked as failed due to missed heartbeats
            response = requests.get("http://127.0.0.1:8000/nodes")
            assert response.status_code == 200
    
    def test_split_brain_scenario(self, service_manager):
        """Test split-brain scenario with multiple gateways"""
        # Start multiple gateways
        gateway1 = service_manager.start_gateway("gateway1", 8000, ["127.0.0.1:8001"])
        gateway2 = service_manager.start_gateway("gateway2", 8001, ["127.0.0.1:8000"])
        
        # Start KV stores connected to different gateways
        kvstore1 = service_manager.start_kvstore("kvstore1", 8080, "127.0.0.1:8000")
        kvstore2 = service_manager.start_kvstore("kvstore2", 8081, "127.0.0.1:8001")
        
        time.sleep(3)
        
        # Simulate network partition between gateways
        with patch('requests.post') as mock_post:
            # Block inter-gateway communication
            def side_effect(*args, **kwargs):
                url = args[0] if args else kwargs.get('url', '')
                if '8001' in url or '8000' in url:
                    raise requests.ConnectionError("Partition")
                return mock_post.return_value
            
            mock_post.side_effect = side_effect
            
            # Both gateways should still work independently
            response1 = requests.get("http://127.0.0.1:8000/health")
            response2 = requests.get("http://127.0.0.1:8001/health")
            
            assert response1.status_code == 200
            assert response2.status_code == 200


@pytest.mark.chaos
class TestResourceExhaustion:
    """Test system behavior under resource constraints"""
    
    def test_memory_pressure(self, service_manager):
        """Test behavior under memory pressure"""
        # Start system
        gateway = service_manager.start_gateway("gateway1", 8000)
        
        kvstores = []
        for i in range(2):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                8080 + i,
                "127.0.0.1:8000"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Store large amounts of data to simulate memory pressure
        large_data = "x" * (1024 * 1024)  # 1MB string
        stored_count = 0
        
        for i in range(100):  # Try to store 100MB
            key = f"large_key_{i}"
            
            try:
                response = requests.get(f"http://127.0.0.1:8000/nodes/{key}")
                if response.status_code == 200:
                    node_data = response.json()
                    kvstore_port = node_data["port"]
                    
                    response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                        json={"key": key, "value": large_data},
                        timeout=5
                    )
                    
                    if response.status_code == 200:
                        stored_count += 1
                    
            except Exception as e:
                print(f"Failed to store large key {i}: {e}")
                break
        
        print(f"Successfully stored {stored_count} large objects")
        
        # System should still be responsive
        response = requests.get("http://127.0.0.1:8000/health")
        assert response.status_code == 200
        
        # Should be able to store small objects
        response = requests.get("http://127.0.0.1:8000/nodes/small_key")
        if response.status_code == 200:
            node_data = response.json()
            kvstore_port = node_data["port"]
            
            response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                json={"key": "small_key", "value": "small_value"}
            )
            assert response.status_code == 200
    
    def test_high_connection_load(self, service_manager):
        """Test system under high connection load"""
        # Start system
        gateway = service_manager.start_gateway("gateway1", 8000)
        
        kvstores = []
        for i in range(3):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                8080 + i,
                "127.0.0.1:8000"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Create many concurrent connections
        def worker(worker_id):
            """Worker function to create load"""
            try:
                for i in range(10):
                    key = f"load_key_{worker_id}_{i}"
                    
                    # Get node
                    response = requests.get(f"http://127.0.0.1:8000/nodes/{key}", timeout=1)
                    if response.status_code == 200:
                        node_data = response.json()
                        kvstore_port = node_data["port"]
                        
                        # Store data
                        requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                            json={"key": key, "value": f"value_{worker_id}_{i}"},
                            timeout=1
                        )
                        
                        # Read data back
                        requests.get(f"http://127.0.0.1:{kvstore_port}/get/{key}", timeout=1)
                        
            except Exception as e:
                print(f"Worker {worker_id} failed: {e}")
        
        # Start many concurrent workers
        threads = []
        for worker_id in range(50):
            t = threading.Thread(target=worker, args=[worker_id])
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join(timeout=30)
        
        # System should still be responsive
        response = requests.get("http://127.0.0.1:8000/health")
        assert response.status_code == 200


@pytest.mark.chaos
class TestCorruptionAndInconsistency:
    """Test handling of data corruption and inconsistency"""
    
    def test_hash_ring_corruption(self, service_manager):
        """Test behavior when hash ring becomes corrupted"""
        # Start system
        gateway = service_manager.start_gateway("gateway1", 8000)
        
        kvstores = []
        for i in range(3):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                8080 + i,
                "127.0.0.1:8000"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Store some data first
        test_keys = [f"corrupt_key_{i}" for i in range(20)]
        for key in test_keys:
            response = requests.get(f"http://127.0.0.1:8000/nodes/{key}")
            if response.status_code == 200:
                node_data = response.json()
                kvstore_port = node_data["port"]
                
                requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                    json={"key": key, "value": f"value_{key}"}
                )
        
        # Simulate hash ring corruption by removing/adding nodes rapidly
        for _ in range(5):
            # Add and immediately remove a node
            temp_kvstore = service_manager.start_kvstore(
                f"temp_kvstore_{random.randint(1000, 9999)}",
                8090 + random.randint(0, 10),
                "127.0.0.1:8000"
            )
            time.sleep(0.5)
            temp_kvstore.stop()
            time.sleep(0.5)
        
        # System should recover and still be functional
        time.sleep(5)
        
        response = requests.get("http://127.0.0.1:8000/health")
        assert response.status_code == 200
        
        # Should still be able to get node assignments
        response = requests.get("http://127.0.0.1:8000/nodes/test_key")
        assert response.status_code in [200, 404]  # Should not crash
    
    def test_inconsistent_data_across_nodes(self, service_manager):
        """Test behavior when nodes have inconsistent data"""
        # Start system
        gateway = service_manager.start_gateway("gateway1", 8000)
        
        kvstores = []
        for i in range(3):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                8080 + i,
                "127.0.0.1:8000"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Deliberately create inconsistent data by storing same key on different nodes
        test_key = "inconsistent_key"
        
        # Store different values on different nodes
        for i, port in enumerate([8080, 8081, 8082]):
            try:
                requests.post(f"http://127.0.0.1:{port}/put",
                    json={"key": test_key, "value": f"inconsistent_value_{i}"},
                    timeout=2
                )
            except Exception as e:
                print(f"Failed to create inconsistency on port {port}: {e}")
        
        # System should still be able to handle requests
        response = requests.get(f"http://127.0.0.1:8000/nodes/{test_key}")
        if response.status_code == 200:
            node_data = response.json()
            kvstore_port = node_data["port"]
            
            # Should get some value (whichever the hash ring determines)
            response = requests.get(f"http://127.0.0.1:{kvstore_port}/get/{test_key}")
            # Should either succeed or fail gracefully
            assert response.status_code in [200, 404]


@pytest.mark.chaos
class TestTimeoutAndLatency:
    """Test system behavior under high latency and timeouts"""
    
    def test_slow_node_responses(self, service_manager):
        """Test behavior when nodes respond slowly"""
        # Start system
        gateway = service_manager.start_gateway("gateway1", 8000)
        
        kvstores = []
        for i in range(3):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                8080 + i,
                "127.0.0.1:8000"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Simulate slow responses by introducing delays
        with patch('requests.post') as mock_post, patch('requests.get') as mock_get:
            # Add delays to some requests
            def slow_post(*args, **kwargs):
                if random.random() < 0.3:  # 30% of requests are slow
                    time.sleep(2)
                return mock_post.return_value
            
            def slow_get(*args, **kwargs):
                if random.random() < 0.3:
                    time.sleep(2)
                return mock_get.return_value
            
            mock_post.side_effect = slow_post
            mock_get.side_effect = slow_get
            
            # Try to perform operations
            success_count = 0
            for i in range(20):
                try:
                    key = f"slow_key_{i}"
                    
                    # This should work despite some slow responses
                    response = requests.get(f"http://127.0.0.1:8000/nodes/{key}", timeout=5)
                    if response.status_code == 200:
                        success_count += 1
                        
                except Exception as e:
                    print(f"Request {i} failed: {e}")
            
            # Should have some successes
            assert success_count > 0
    
    def test_heartbeat_timeout_edge_cases(self, service_manager):
        """Test edge cases around heartbeat timeouts"""
        # Start system with custom timeout
        gateway = service_manager.start_gateway("gateway1", 8000)
        
        kvstore = service_manager.start_kvstore("kvstore1", 8080, "127.0.0.1:8000")
        
        time.sleep(2)
        
        # Verify node is registered
        response = requests.get("http://127.0.0.1:8000/nodes")
        assert response.status_code == 200
        nodes = response.json()["nodes"]
        assert "kvstore1" in nodes
        
        # Stop sending heartbeats by mocking the heartbeat function
        with patch.object(kvstore, '_send_heartbeat') as mock_heartbeat:
            mock_heartbeat.return_value = False  # Simulate failed heartbeats
            
            # Wait for timeout detection
            time.sleep(35)
            
            # Gateway should detect the timeout
            response = requests.get("http://127.0.0.1:8000/nodes")
            assert response.status_code == 200
            nodes = response.json()["nodes"]
            
            # Node might be marked as dead or removed
            if "kvstore1" in nodes:
                assert nodes["kvstore1"]["status"] in ["dead", "inactive"] 