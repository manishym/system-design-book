"""
Unit tests for KVStoreService
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from storage.kvstore.kvstore_service import KVStoreService


class TestKVStoreService:
    """Test KVStoreService class"""
    
    def test_kvstore_initialization(self):
        """Test KV store service initialization"""
        service = KVStoreService("node1", 8080, "127.0.0.1:8000")
        
        assert service.node_id == "node1"
        assert service.listen_port == 8080
        assert service.gateway_address == "127.0.0.1:8000"
        assert service.listen_address == "0.0.0.0"
        assert len(service.data) == 0
        assert service.running == False
        assert service.registered == False
        assert service.app is not None
    
    def test_store_and_retrieve_data(self):
        """Test storing and retrieving key-value pairs"""
        service = KVStoreService("node1", 8080, "127.0.0.1:8000")
        
        # Store data directly
        with service.data_lock:
            service.data["test_key"] = "test_value"
            service.data["number_key"] = 42
            service.data["dict_key"] = {"nested": "value"}
        
        # Retrieve data
        with service.data_lock:
            assert service.data["test_key"] == "test_value"
            assert service.data["number_key"] == 42
            assert service.data["dict_key"] == {"nested": "value"}
    
    def test_concurrent_data_access(self):
        """Test thread-safe access to data store"""
        service = KVStoreService("node1", 8080, "127.0.0.1:8000")
        
        def write_data(key, value):
            with service.data_lock:
                service.data[key] = value
        
        def read_data(key):
            with service.data_lock:
                return service.data.get(key)
        
        # Start multiple threads writing data
        threads = []
        for i in range(10):
            t = threading.Thread(target=write_data, args=[f"key{i}", f"value{i}"])
            threads.append(t)
            t.start()
        
        # Wait for all writes to complete
        for t in threads:
            t.join()
        
        # Verify all data was written
        with service.data_lock:
            for i in range(10):
                assert service.data[f"key{i}"] == f"value{i}"
    
    def test_flask_routes_setup(self):
        """Test that Flask routes are properly set up"""
        service = KVStoreService("node1", 8080, "127.0.0.1:8000")
        
        # Check that Flask app exists
        assert service.app is not None
        
        # Get the route rules
        routes = [rule.rule for rule in service.app.url_map.iter_rules()]
        
        # Check for expected routes
        expected_routes = ['/put', '/get/<key>', '/delete/<key>', '/keys', '/health', '/stats']
        for route in expected_routes:
            route_found = any(route in r for r in routes)
            assert route_found, f"Route {route} not found in {routes}"
    
    @patch('storage.kvstore.kvstore_service.requests.post')
    def test_register_with_gateway_success(self, mock_post):
        """Test successful registration with gateway"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        service = KVStoreService("node1", 8080, "127.0.0.1:8000")
        
        result = service._register_with_gateway()
        
        assert result == True
        assert service.registered == True
        
        # Verify the POST request was made with correct data
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]['json']['node_id'] == "node1"
        assert call_args[1]['json']['address'] == "0.0.0.0"
        assert call_args[1]['json']['port'] == 8080
    
    @patch('storage.kvstore.kvstore_service.requests.post')
    def test_register_with_gateway_failure(self, mock_post):
        """Test failed registration with gateway"""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        service = KVStoreService("node1", 8080, "127.0.0.1:8000")
        
        result = service._register_with_gateway()
        
        assert result == False
        assert service.registered == False
    
    @patch('storage.kvstore.kvstore_service.requests.post')
    def test_register_with_gateway_network_error(self, mock_post):
        """Test registration with network error"""
        # Mock network exception
        mock_post.side_effect = Exception("Network error")
        
        service = KVStoreService("node1", 8080, "127.0.0.1:8000")
        
        result = service._register_with_gateway()
        
        assert result == False
        assert service.registered == False
    
    @patch('storage.kvstore.kvstore_service.requests.post')
    def test_send_heartbeat_success(self, mock_post):
        """Test successful heartbeat sending"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        service = KVStoreService("node1", 8080, "127.0.0.1:8000")
        service.data["test"] = "value"  # Add some data
        
        result = service._send_heartbeat()
        
        assert result == True
        
        # Verify heartbeat data
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        heartbeat_data = call_args[1]['json']
        assert heartbeat_data['node_id'] == "node1"
        assert heartbeat_data['address'] == "0.0.0.0"
        assert heartbeat_data['port'] == 8080
        assert heartbeat_data['key_count'] == 1
        assert 'timestamp' in heartbeat_data
    
    @patch('storage.kvstore.kvstore_service.requests.post')
    def test_send_heartbeat_failure(self, mock_post):
        """Test failed heartbeat sending"""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        service = KVStoreService("node1", 8080, "127.0.0.1:8000")
        
        result = service._send_heartbeat()
        
        assert result == False


class TestKVStoreHTTPEndpoints:
    """Test KV store HTTP endpoints using Flask test client"""
    
    @pytest.fixture
    def service(self):
        """Create a KV store service for testing"""
        return KVStoreService("test-node", 8080, "127.0.0.1:8000")
    
    def test_put_endpoint_success(self, service):
        """Test successful PUT operation"""
        with service.app.test_client() as client:
            response = client.post('/put', 
                json={"key": "test_key", "value": "test_value"}
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "stored"
            assert data["key"] == "test_key"
            assert data["node_id"] == "test-node"
            
            # Verify data was actually stored
            with service.data_lock:
                assert service.data["test_key"] == "test_value"
    
    def test_put_endpoint_missing_key(self, service):
        """Test PUT operation with missing key"""
        with service.app.test_client() as client:
            response = client.post('/put', 
                json={"value": "test_value"}
            )
            
            assert response.status_code == 400
            data = response.get_json()
            assert "error" in data
    
    def test_put_endpoint_various_data_types(self, service):
        """Test PUT operation with various data types"""
        test_cases = [
            ("string_key", "string_value"),
            ("int_key", 42),
            ("float_key", 3.14),
            ("bool_key", True),
            ("list_key", [1, 2, 3]),
            ("dict_key", {"nested": "value"}),
            ("null_key", None)
        ]
        
        with service.app.test_client() as client:
            for key, value in test_cases:
                response = client.post('/put', 
                    json={"key": key, "value": value}
                )
                
                assert response.status_code == 200
                
                # Verify stored value
                with service.data_lock:
                    assert service.data[key] == value
    
    def test_get_endpoint_success(self, service):
        """Test successful GET operation"""
        # Store data first
        with service.data_lock:
            service.data["test_key"] = "test_value"
        
        with service.app.test_client() as client:
            response = client.get('/get/test_key')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["value"] == "test_value"
            assert data["key"] == "test_key"
            assert data["node_id"] == "test-node"
    
    def test_get_endpoint_key_not_found(self, service):
        """Test GET operation for non-existent key"""
        with service.app.test_client() as client:
            response = client.get('/get/nonexistent_key')
            
            assert response.status_code == 404
            data = response.get_json()
            assert "error" in data
    
    def test_delete_endpoint_success(self, service):
        """Test successful DELETE operation"""
        # Store data first
        with service.data_lock:
            service.data["test_key"] = "test_value"
        
        with service.app.test_client() as client:
            response = client.delete('/delete/test_key')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "deleted"
            assert data["key"] == "test_key"
            assert data["node_id"] == "test-node"
            
            # Verify data was actually deleted
            with service.data_lock:
                assert "test_key" not in service.data
    
    def test_delete_endpoint_key_not_found(self, service):
        """Test DELETE operation for non-existent key"""
        with service.app.test_client() as client:
            response = client.delete('/delete/nonexistent_key')
            
            assert response.status_code == 404
            data = response.get_json()
            assert "error" in data
    
    def test_keys_endpoint(self, service):
        """Test listing all keys"""
        # Store some data
        test_data = {
            "key1": "value1",
            "key2": "value2",
            "key3": "value3"
        }
        
        with service.data_lock:
            service.data.update(test_data)
        
        with service.app.test_client() as client:
            response = client.get('/keys')
            
            assert response.status_code == 200
            data = response.get_json()
            assert "keys" in data
            assert "count" in data
            assert "node_id" in data
            assert data["count"] == 3
            assert data["node_id"] == "test-node"
            assert set(data["keys"]) == set(test_data.keys())
    
    def test_keys_endpoint_empty(self, service):
        """Test listing keys when store is empty"""
        with service.app.test_client() as client:
            response = client.get('/keys')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["keys"] == []
            assert data["count"] == 0
    
    def test_health_endpoint(self, service):
        """Test health check endpoint"""
        with service.app.test_client() as client:
            response = client.get('/health')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "healthy"
            assert data["node_id"] == "test-node"
            assert data["registered"] == False
            assert data["key_count"] == 0
    
    def test_stats_endpoint(self, service):
        """Test statistics endpoint"""
        # Add some data
        with service.data_lock:
            service.data["key1"] = "value1"
            service.data["key2"] = "value2"
        
        service.registered = True
        
        with service.app.test_client() as client:
            response = client.get('/stats')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["node_id"] == "test-node"
            assert data["address"] == "0.0.0.0:8080"
            assert data["key_count"] == 2
            assert data["registered"] == True
            assert data["gateway"] == "127.0.0.1:8000"
            assert "uptime" in data


class TestKVStoreIntegration:
    """Integration tests for KV store operations"""
    
    def test_full_crud_cycle(self):
        """Test complete CRUD cycle"""
        service = KVStoreService("test-node", 8080, "127.0.0.1:8000")
        
        with service.app.test_client() as client:
            # CREATE - Store a value
            response = client.post('/put', 
                json={"key": "user:123", "value": {"name": "John", "age": 30}}
            )
            assert response.status_code == 200
            
            # READ - Retrieve the value
            response = client.get('/get/user:123')
            assert response.status_code == 200
            data = response.get_json()
            assert data["value"] == {"name": "John", "age": 30}
            
            # UPDATE - Modify the value
            response = client.post('/put', 
                json={"key": "user:123", "value": {"name": "John", "age": 31}}
            )
            assert response.status_code == 200
            
            # Verify update
            response = client.get('/get/user:123')
            assert response.status_code == 200
            data = response.get_json()
            assert data["value"]["age"] == 31
            
            # DELETE - Remove the value
            response = client.delete('/delete/user:123')
            assert response.status_code == 200
            
            # Verify deletion
            response = client.get('/get/user:123')
            assert response.status_code == 404
    
    def test_concurrent_operations(self):
        """Test concurrent operations on the same key"""
        service = KVStoreService("test-node", 8080, "127.0.0.1:8000")
        
        def update_counter():
            with service.app.test_client() as client:
                for i in range(10):
                    # Read current value
                    response = client.get('/get/counter')
                    if response.status_code == 200:
                        current = response.get_json()["value"]
                    else:
                        current = 0
                    
                    # Increment and store
                    client.post('/put', 
                        json={"key": "counter", "value": current + 1}
                    )
        
        # Start multiple threads
        threads = []
        for _ in range(5):
            t = threading.Thread(target=update_counter)
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Final counter should be > 0 (exact value depends on race conditions)
        with service.app.test_client() as client:
            response = client.get('/get/counter')
            if response.status_code == 200:
                final_value = response.get_json()["value"]
                assert final_value > 0
    
    def test_large_data_storage(self):
        """Test storing and retrieving large data"""
        service = KVStoreService("test-node", 8080, "127.0.0.1:8000")
        
        # Create large data structure
        large_data = {
            "users": [{"id": i, "name": f"user{i}", "data": "x" * 1000} for i in range(100)],
            "metadata": {"size": 100, "version": "1.0"}
        }
        
        with service.app.test_client() as client:
            # Store large data
            response = client.post('/put', 
                json={"key": "large_dataset", "value": large_data}
            )
            assert response.status_code == 200
            
            # Retrieve and verify
            response = client.get('/get/large_dataset')
            assert response.status_code == 200
            retrieved_data = response.get_json()["value"]
            assert retrieved_data == large_data
    
    def test_special_key_characters(self):
        """Test keys with special characters"""
        service = KVStoreService("test-node", 8080, "127.0.0.1:8000")
        
        special_keys = [
            "key:with:colons",
            "key.with.dots", 
            "key-with-dashes",
            "key_with_underscores",
            "key/with/slashes",
            "key with spaces",
            "key@with#symbols$",
            "123numeric_key",
            "UPPERCASE_KEY",
            "MiXeD_cAsE_kEy"
        ]
        
        with service.app.test_client() as client:
            # Store values with special keys
            for key in special_keys:
                response = client.post('/put', 
                    json={"key": key, "value": f"value_for_{key}"}
                )
                assert response.status_code == 200
            
            # Retrieve and verify all keys (using POST for special characters)
            for key in special_keys:
                # Use POST method for keys with special characters
                response = client.post('/get', json={"key": key})
                assert response.status_code == 200
                data = response.get_json()
                assert data["value"] == f"value_for_{key}"
            
            # Test deletion with POST method for special characters
            for key in special_keys[:3]:  # Test a few deletions
                response = client.post('/delete', json={"key": key})
                assert response.status_code == 200
                
                # Verify deletion
                response = client.post('/get', json={"key": key})
                assert response.status_code == 404
    
    @patch('storage.kvstore.kvstore_service.requests.post')
    def test_heartbeat_integration(self, mock_post):
        """Test heartbeat integration with data operations"""
        # Mock successful heartbeat
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        service = KVStoreService("test-node", 8080, "127.0.0.1:8000")
        
        with service.app.test_client() as client:
            # Store some data
            for i in range(5):
                response = client.post('/put', 
                    json={"key": f"key{i}", "value": f"value{i}"}
                )
                assert response.status_code == 200
            
            # Send heartbeat
            result = service._send_heartbeat()
            assert result == True
            
            # Verify heartbeat included correct key count
            call_args = mock_post.call_args
            heartbeat_data = call_args[1]['json']
            assert heartbeat_data['key_count'] == 5 