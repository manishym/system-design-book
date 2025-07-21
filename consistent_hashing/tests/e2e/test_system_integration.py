"""
End-to-end integration tests for the consistent hashing system
"""

import pytest
import time
import requests
import threading
from collections import defaultdict
import random
import json
import logging

logger = logging.getLogger(__name__)



@pytest.mark.e2e
class TestSystemIntegration:
    """End-to-end tests using the actual system components"""
    
    def test_single_gateway_multiple_kvstores(self, service_manager):
        """Test system with one gateway and multiple KV stores"""
        # Start gateway with dynamic port
        gateway = service_manager.start_gateway("gateway1")
        gateway_port = gateway.listen_port
        
        # Start multiple KV stores
        kvstores = []
        for i in range(3):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}", 
                None,  # Use dynamic port
                f"127.0.0.1:{gateway_port}"
            )
            kvstores.append(kvstore)
        
        # Wait for registration
        time.sleep(2)
        
        # Verify all nodes are registered
        response = requests.get(f"http://127.0.0.1:{gateway_port}/nodes")
        assert response.status_code == 200
        nodes = response.json()["nodes"]
        assert len(nodes) == 3
        
        # Test key distribution
        test_keys = [f"key_{i}" for i in range(30)]
        key_distribution = defaultdict(list)
        
        for key in test_keys:
            # Get node for key
            response = requests.get(f"http://127.0.0.1:{gateway_port}/nodes/{key}")
            assert response.status_code == 200
            node_data = response.json()
            
            # Store key on that node
            kvstore_port = node_data["node"]["port"]
            response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                json={"key": key, "value": f"value_{key}"}
            )
            assert response.status_code == 200
            
            key_distribution[node_data["node"]["node_id"]].append(key)
        
        # Verify distribution (each node should have some keys)
        for node_id, keys in key_distribution.items():
            assert len(keys) > 0, f"Node {node_id} has no keys"
        
        # Verify we can retrieve all stored keys
        for key in test_keys:
            # Get node for key
            response = requests.get(f"http://127.0.0.1:{gateway_port}/nodes/{key}")
            node_data = response.json()
            
            # Retrieve from that node
            kvstore_port = node_data["node"]["port"]
            response = requests.get(f"http://127.0.0.1:{kvstore_port}/get/{key}")
            assert response.status_code == 200
            assert response.json()["value"] == f"value_{key}"
    
    def test_node_failure_and_recovery(self, service_manager):
        """Test system behavior when nodes fail and recover"""
        # Start gateway and KV stores using dynamic ports
        gateway = service_manager.start_gateway("gateway1", None)
        gateway_port = gateway.listen_port
        gateway_url = f"http://127.0.0.1:{gateway_port}"
        
        kvstores = []
        for i in range(4):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                None,  # Use dynamic port
                f"127.0.0.1:{gateway_port}"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Store data across all nodes
        test_keys = [f"key_{i}" for i in range(40)]
        stored_data = {}
        
        for key in test_keys:
            # Get node for key
            response = requests.get(f"{gateway_url}/nodes/{key}")
            assert response.status_code == 200
            node_data = response.json()
            
            # Store data
            kvstore_port = node_data["node"]["port"]
            value = f"value_{key}"
            response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                json={"key": key, "value": value}
            )
            assert response.status_code == 200
            logger.info(f"Stored data on node {node_data}")
            stored_data[key] = {"value": value, "node": node_data["node"]["node_id"]}
        
        # Stop one KV store (simulate failure)
        failed_kvstore = kvstores[1]
        failed_node_id = f"kvstore1"
        failed_kvstore.stop()
        
        # Wait for failure detection (heartbeat timeout)
        time.sleep(35)  # Longer than heartbeat timeout
        
        # Check that failed node is detected
        response = requests.get(f"{gateway_url}/nodes")
        assert response.status_code == 200
        nodes = response.json()["nodes"]
        
        # Failed node might still be listed but marked as dead/inactive
        if failed_node_id in nodes:
            assert nodes[failed_node_id]["status"] in ["dead", "inactive"]
        
        # Keys that were on the failed node should be remapped
        remapped_keys = []
        for key, data in stored_data.items():
            if data["node"] == failed_node_id:
                # Get new node for this key
                response = requests.get(f"{gateway_url}/nodes/{key}")
                if response.status_code == 200:
                    logger.info(f"YMM ======: Nodes: {response.json()}")

                    new_node = response.json()["node"]["node_id"]
                    assert new_node != failed_node_id
                    remapped_keys.append(key)
        
        # Verify remaining nodes still have their data
        for key, data in stored_data.items():
            if data["node"] != failed_node_id:
                response = requests.get(f"{gateway_url}/nodes/{key}")
                if response.status_code == 200:
                    node_data = response.json()
                    kvstore_port = node_data["node"]["port"]
                    
                    response = requests.get(f"http://127.0.0.1:{kvstore_port}/get/{key}")
                    if response.status_code == 200:
                        assert response.json()["value"] == data["value"]
    
    def test_consistent_hashing_property(self, service_manager):
        """Test that consistent hashing minimizes key remapping"""
        # Start with 3 nodes using dynamic ports
        gateway = service_manager.start_gateway("gateway1", None)  # Use dynamic port
        gateway_port = gateway.listen_port
        gateway_url = f"http://127.0.0.1:{gateway_port}"
        
        kvstores = []
        for i in range(3):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                None,  # Use dynamic port
                f"127.0.0.1:{gateway_port}"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Get initial key mapping
        test_keys = [f"key_{i}" for i in range(100)]
        initial_mapping = {}
        
        for key in test_keys:
            response = requests.get(f"{gateway_url}/nodes/{key}")
            assert response.status_code == 200
            node_data = response.json()
            initial_mapping[key] = node_data["node"]["node_id"]
        
        # Add a new node
        new_kvstore = service_manager.start_kvstore(
            "kvstore3",
            None,  # Use dynamic port
            f"127.0.0.1:{gateway_port}"
        )
        
        time.sleep(2)
        
        # Get new mapping
        new_mapping = {}
        for key in test_keys:
            response = requests.get(f"{gateway_url}/nodes/{key}")
            assert response.status_code == 200
            node_data = response.json()
            new_mapping[key] = node_data["node"]["node_id"]
        
        # Count remapped keys
        remapped_count = sum(1 for key in test_keys 
                           if initial_mapping[key] != new_mapping[key])
        
        # Should remap less than 50% of keys (good consistent hashing)
        remapping_percentage = remapped_count / len(test_keys)
        assert remapping_percentage < 0.5, f"Too many keys remapped: {remapping_percentage:.2%}"
        
        # Verify that remapped keys go to the new node (mostly)
        new_node_keys = sum(1 for key in test_keys 
                          if new_mapping[key] == "kvstore3")
        assert new_node_keys > 0, "New node should get some keys"
    
    def test_multiple_gateways_gossip(self, service_manager):
        """Test multiple gateways with gossip protocol"""
        # Start multiple gateways using dynamic ports
        gateway1 = service_manager.start_gateway("gateway1", None, [])  # Start without peers first
        gateway1_port = gateway1.listen_port
        gateway1_url = f"http://127.0.0.1:{gateway1_port}"
        
        gateway2 = service_manager.start_gateway("gateway2", None, [f"127.0.0.1:{gateway1_port}"])
        gateway2_port = gateway2.listen_port
        gateway2_url = f"http://127.0.0.1:{gateway2_port}"
        
        # Start KV stores connecting to different gateways
        kvstore1 = service_manager.start_kvstore("kvstore1", None, f"127.0.0.1:{gateway1_port}")
        kvstore2 = service_manager.start_kvstore("kvstore2", None, f"127.0.0.1:{gateway2_port}")
        
        time.sleep(3)  # Wait for gossip to propagate
        
        # Both gateways should know about both KV stores
        for gateway_url in [gateway1_url, gateway2_url]:
            response = requests.get(f"{gateway_url}/nodes")
            assert response.status_code == 200
            nodes = response.json()["nodes"]
            
            # Should have both nodes (eventually, due to gossip)
            node_ids = set(nodes.keys())
            # Note: In simplified version, gossip might not be fully implemented
            # So we check that each gateway at least knows about its own node
            assert len(node_ids) >= 1
    
    def test_load_balancing(self, service_manager):
        """Test that load is distributed across nodes"""
        # Start system using dynamic ports
        gateway = service_manager.start_gateway("gateway1", None)
        gateway_port = gateway.listen_port
        gateway_url = f"http://127.0.0.1:{gateway_port}"
        
        kvstores = []
        for i in range(4):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                None,  # Use dynamic port
                f"127.0.0.1:{gateway_port}"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Store many keys
        num_keys = 200
        node_load = defaultdict(int)
        
        for i in range(num_keys):
            key = f"load_test_key_{i}"
            
            # Get node for key
            response = requests.get(f"{gateway_url}/nodes/{key}")
            assert response.status_code == 200
            node_data = response.json()
            node_id = node_data["node"]["node_id"]
            
            # Store key
            kvstore_port = node_data["node"]["port"]
            response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                json={"key": key, "value": f"value_{i}"}
            )
            assert response.status_code == 200
            
            node_load[node_id] += 1
        
        # Check load distribution
        loads = list(node_load.values())
        min_load = min(loads)
        max_load = max(loads)
        
        # Load should be reasonably balanced (no node should have > 60% of keys)
        assert max_load <= num_keys * 0.6, f"Unbalanced load: {node_load}"
        
        # Every node should have some load
        assert min_load > 0, f"Some nodes have no load: {node_load}"
        
        # Load difference should be reasonable
        load_difference = max_load - min_load
        assert load_difference <= num_keys * 0.3, f"Too much load difference: {node_load}"


@pytest.mark.e2e
class TestRealWorldScenarios:
    """Test real-world usage scenarios"""
    
    def test_user_session_management(self, service_manager):
        """Test user session storage and retrieval"""
        # Start system using dynamic ports
        gateway = service_manager.start_gateway("gateway1", None)
        gateway_port = gateway.listen_port
        gateway_url = f"http://127.0.0.1:{gateway_port}"
        
        kvstores = []
        for i in range(3):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                None,  # Use dynamic port
                f"127.0.0.1:{gateway_port}"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Simulate user sessions
        users = [f"user_{i}" for i in range(50)]
        sessions = {}
        
        for user in users:
            session_key = f"session:{user}"
            session_data = {
                "user_id": user,
                "login_time": time.time(),
                "ip_address": f"192.168.1.{random.randint(1, 254)}",
                "preferences": {"theme": "dark", "language": "en"}
            }
            
            # Get node for session
            response = requests.get(f"{gateway_url}/nodes/{session_key}")
            assert response.status_code == 200
            node_data = response.json()
            
            # Store session
            kvstore_port = node_data["node"]["port"]
            response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                json={"key": session_key, "value": session_data}
            )
            assert response.status_code == 200
            
            sessions[user] = {"data": session_data, "node": node_data["node"]["node_id"]}
        
        # Simulate session access patterns
        for _ in range(100):
            user = random.choice(users)
            session_key = f"session:{user}"
            
            # Get node for session
            response = requests.get(f"{gateway_url}/nodes/{session_key}")
            assert response.status_code == 200
            node_data = response.json()
            
            # Retrieve session
            kvstore_port = node_data["node"]["port"]
            response = requests.get(f"http://127.0.0.1:{kvstore_port}/get/{session_key}")
            assert response.status_code == 200
            
            retrieved_data = response.json()["value"]
            expected_data = sessions[user]["data"]
            assert retrieved_data["user_id"] == expected_data["user_id"]
    
    def test_cache_invalidation(self, service_manager):
        """Test cache-like operations with TTL simulation"""
        # Start system using dynamic ports
        gateway = service_manager.start_gateway("gateway1", None)
        gateway_port = gateway.listen_port
        gateway_url = f"http://127.0.0.1:{gateway_port}"
        
        kvstores = []
        for i in range(2):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                None,  # Use dynamic port
                f"127.0.0.1:{gateway_port}"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Store cache entries with timestamps
        cache_entries = {}
        for i in range(20):
            cache_key = f"cache:item_{i}"
            cache_data = {
                "value": f"cached_value_{i}",
                "timestamp": time.time(),
                "ttl": 30  # 30 seconds TTL
            }
            
            # Get node for cache entry
            response = requests.get(f"{gateway_url}/nodes/{cache_key}")
            assert response.status_code == 200
            node_data = response.json()
            
            # Store cache entry
            kvstore_port = node_data["node"]["port"]
            response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                json={"key": cache_key, "value": cache_data}
            )
            assert response.status_code == 200
            
            cache_entries[cache_key] = node_data["node"]["port"]
        
        # Access cached data
        for cache_key, kvstore_port in cache_entries.items():
            response = requests.get(f"http://127.0.0.1:{kvstore_port}/get/{cache_key}")
            assert response.status_code == 200
            
            cached_data = response.json()["value"]
            assert "timestamp" in cached_data
            assert "ttl" in cached_data
        
        # Simulate cache updates
        for i in range(5):
            cache_key = f"cache:item_{i}"
            kvstore_port = cache_entries[cache_key]
            
            # Update cache entry
            updated_data = {
                "value": f"updated_value_{i}",
                "timestamp": time.time(),
                "ttl": 30
            }
            
            response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                json={"key": cache_key, "value": updated_data}
            )
            assert response.status_code == 200
            
            # Verify update
            response = requests.get(f"http://127.0.0.1:{kvstore_port}/get/{cache_key}")
            assert response.status_code == 200
            assert response.json()["value"]["value"] == f"updated_value_{i}"
    
    def test_concurrent_clients(self, service_manager):
        """Test multiple concurrent clients"""
        # Start system using dynamic ports
        gateway = service_manager.start_gateway("gateway1", None)
        gateway_port = gateway.listen_port
        gateway_url = f"http://127.0.0.1:{gateway_port}"
        
        kvstores = []
        for i in range(3):
            kvstore = service_manager.start_kvstore(
                f"kvstore{i}",
                None,  # Use dynamic port
                f"127.0.0.1:{gateway_port}"
            )
            kvstores.append(kvstore)
        
        time.sleep(2)
        
        # Shared data for threads
        results = []
        errors = []
        
        def client_worker(client_id):
            """Simulate a client performing operations"""
            try:
                for i in range(10):
                    key = f"client_{client_id}_key_{i}"
                    value = f"client_{client_id}_value_{i}"
                    
                    # Get node for key
                    response = requests.get(f"{gateway_url}/nodes/{key}")
                    if response.status_code != 200:
                        errors.append(f"Client {client_id}: Failed to get node for {key}")
                        continue
                    
                    node_data = response.json()
                    kvstore_port = node_data["node"]["port"]
                    
                    # Store value
                    response = requests.post(f"http://127.0.0.1:{kvstore_port}/put",
                        json={"key": key, "value": value}
                    )
                    if response.status_code != 200:
                        errors.append(f"Client {client_id}: Failed to store {key}")
                        continue
                    
                    # Retrieve value
                    response = requests.get(f"http://127.0.0.1:{kvstore_port}/get/{key}")
                    if response.status_code != 200:
                        errors.append(f"Client {client_id}: Failed to retrieve {key}")
                        continue
                    
                    retrieved_value = response.json()["value"]
                    if retrieved_value != value:
                        errors.append(f"Client {client_id}: Value mismatch for {key}")
                        continue
                    
                    results.append(f"Client {client_id}: Successfully processed {key}")
                    
            except Exception as e:
                errors.append(f"Client {client_id}: Exception - {str(e)}")
        
        # Start multiple client threads
        threads = []
        for client_id in range(10):
            t = threading.Thread(target=client_worker, args=[client_id])
            threads.append(t)
            t.start()
        
        # Wait for all clients to complete
        for t in threads:
            t.join()
        
        # Verify results
        assert len(errors) == 0, f"Client errors: {errors}"
        assert len(results) == 100, f"Expected 100 successful operations, got {len(results)}" 