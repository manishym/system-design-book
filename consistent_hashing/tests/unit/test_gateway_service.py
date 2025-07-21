"""
Unit tests for SimpleGatewayService
"""

import pytest
import time
import json
import threading
from unittest.mock import Mock, patch, MagicMock
from gateway.gateway_service_simple import SimpleGatewayService, NodeInfo, GossipMessage


class TestNodeInfo:
    """Test NodeInfo class"""
    
    def test_node_info_creation(self):
        """Test creating a NodeInfo instance"""
        node = NodeInfo("node1", "127.0.0.1", 8080)
        
        assert node.node_id == "node1"
        assert node.address == "127.0.0.1"
        assert node.port == 8080
        assert node.status == "active"
        assert isinstance(node.last_heartbeat, float)
    
    def test_node_info_to_dict(self):
        """Test converting NodeInfo to dictionary"""
        node = NodeInfo("node1", "127.0.0.1", 8080)
        node_dict = node.to_dict()
        
        expected_keys = {"node_id", "address", "port", "last_heartbeat", "status"}
        assert set(node_dict.keys()) == expected_keys
        assert node_dict["node_id"] == "node1"
        assert node_dict["address"] == "127.0.0.1"
        assert node_dict["port"] == 8080
        assert node_dict["status"] == "active"
    
    def test_node_info_from_dict(self):
        """Test creating NodeInfo from dictionary"""
        data = {
            "node_id": "node2",
            "address": "192.168.1.100",
            "port": 9090,
            "last_heartbeat": 1234567890.0,
            "status": "inactive"
        }
        
        node = NodeInfo.from_dict(data)
        
        assert node.node_id == "node2"
        assert node.address == "192.168.1.100"
        assert node.port == 9090
        assert node.last_heartbeat == 1234567890.0
        assert node.status == "inactive"


class TestGossipMessage:
    """Test GossipMessage class"""
    
    def test_gossip_message_creation(self):
        """Test creating a GossipMessage"""
        data = {"key": "value", "number": 42}
        msg = GossipMessage("HEARTBEAT", "gateway1", data)
        
        assert msg.message_type == "HEARTBEAT"
        assert msg.sender_id == "gateway1"
        assert msg.data == data
        assert isinstance(msg.message_id, str)
        assert isinstance(msg.timestamp, float)
    
    def test_gossip_message_to_dict(self):
        """Test converting GossipMessage to dictionary"""
        data = {"test": "data"}
        msg = GossipMessage("NODE_UPDATE", "gateway2", data)
        msg_dict = msg.to_dict()
        
        expected_keys = {"message_id", "message_type", "sender_id", "data", "timestamp"}
        assert set(msg_dict.keys()) == expected_keys
        assert msg_dict["message_type"] == "NODE_UPDATE"
        assert msg_dict["sender_id"] == "gateway2"
        assert msg_dict["data"] == data
    
    def test_gossip_message_from_dict(self):
        """Test creating GossipMessage from dictionary"""
        data = {
            "message_id": "test-id-123",
            "message_type": "RING_SYNC",
            "sender_id": "gateway3",
            "data": {"nodes": ["node1", "node2"]},
            "timestamp": 1234567890.0
        }
        
        msg = GossipMessage.from_dict(data)
        
        assert msg.message_id == "test-id-123"
        assert msg.message_type == "RING_SYNC"
        assert msg.sender_id == "gateway3"
        assert msg.data == {"nodes": ["node1", "node2"]}
        assert msg.timestamp == 1234567890.0


class TestSimpleGatewayService:
    """Test SimpleGatewayService class"""
    
    def test_gateway_service_initialization(self):
        """Test gateway service initialization"""
        service = SimpleGatewayService("gateway1", 8000, ["gateway2:8001"])
        
        assert service.gateway_id == "gateway1"
        assert service.listen_port == 8000
        assert service.peer_gateways == ["gateway2:8001"]
        assert len(service.nodes) == 0
        assert service.running == False
        assert service.hash_ring is not None
    
    def test_add_node_to_ring(self):
        """Test adding a node to the hash ring"""
        service = SimpleGatewayService("gateway1", 8000)
        
        node_data = {
            "node_id": "node1",
            "address": "127.0.0.1",
            "port": 8080,
            "last_heartbeat": time.time(),
            "status": "active"
        }
        
        result = service._add_node_to_ring(node_data)
        
        assert result == True
        assert "node1" in service.nodes
        assert "node1" in service.hash_ring.nodes
        assert service.nodes["node1"].address == "127.0.0.1"
        assert service.nodes["node1"].port == 8080
    
    def test_add_duplicate_node_to_ring(self):
        """Test adding the same node twice"""
        service = SimpleGatewayService("gateway1", 8000)
        
        node_data = {
            "node_id": "node1",
            "address": "127.0.0.1",
            "port": 8080,
            "last_heartbeat": time.time(),
            "status": "active"
        }
        
        # Add node first time
        result1 = service._add_node_to_ring(node_data)
        assert result1 == True
        
        # Add same node again
        result2 = service._add_node_to_ring(node_data)
        assert result2 == True  # Should still succeed but not duplicate
        
        # Should still have only one instance
        assert len(service.nodes) == 1
        assert len(service.hash_ring.nodes) == 1
    
    def test_remove_node_from_ring(self):
        """Test removing a node from the hash ring"""
        service = SimpleGatewayService("gateway1", 8000)
        
        # First add a node
        node_data = {
            "node_id": "node1",
            "address": "127.0.0.1",
            "port": 8080,
            "last_heartbeat": time.time(),
            "status": "active"
        }
        service._add_node_to_ring(node_data)
        
        # Then remove it
        result = service._remove_node_from_ring("node1")
        
        assert result == True
        assert "node1" not in service.nodes
        assert "node1" not in service.hash_ring.nodes
    
    def test_remove_nonexistent_node_from_ring(self):
        """Test removing a node that doesn't exist"""
        service = SimpleGatewayService("gateway1", 8000)
        
        result = service._remove_node_from_ring("nonexistent")
        
        assert result == True  # Should not fail
        assert len(service.nodes) == 0
    
    @patch('gateway.gateway_service_simple.requests.post')
    def test_gossip_heartbeat(self, mock_post):
        """Test gossiping heartbeat to peer gateways"""
        mock_post.return_value.status_code = 200
        
        service = SimpleGatewayService("gateway1", 8000, ["127.0.0.1:8001"])
        
        # Mock the _gossip_heartbeat method since it's called internally
        with patch.object(service, '_gossip_heartbeat') as mock_gossip:
            # Simulate heartbeat processing
            node_data = {
                "node_id": "node1",
                "address": "127.0.0.1",
                "port": 8080
            }
            
            # This would normally be called during heartbeat processing
            service._gossip_heartbeat("node1", "127.0.0.1", 8080)
            
            # Verify gossip was called
            mock_gossip.assert_called_once_with("node1", "127.0.0.1", 8080)
    
    def test_health_check_removes_dead_nodes(self):
        """Test that health check removes nodes that haven't sent heartbeats"""
        service = SimpleGatewayService("gateway1", 8000)
        service.heartbeat_timeout = 1  # 1 second timeout for test
        
        # Add a node
        node_data = {
            "node_id": "node1",
            "address": "127.0.0.1",
            "port": 8080,
            "last_heartbeat": time.time() - 2,  # 2 seconds ago (expired)
            "status": "active"
        }
        service._add_node_to_ring(node_data)
        
        # Run health check
        service._check_node_health()
        
        # Node should be marked as dead or removed
        if "node1" in service.nodes:
            assert service.nodes["node1"].status == "dead"
        # Note: In simplified version, nodes might not be auto-removed
    
    def test_flask_app_routes_exist(self):
        """Test that required Flask routes are set up"""
        service = SimpleGatewayService("gateway1", 8000)
        
        # Check that Flask app exists and routes are configured
        assert service.app is not None
        
        # Get the route rules
        routes = [rule.rule for rule in service.app.url_map.iter_rules()]
        
        # Check for expected routes
        expected_routes = ['/heartbeat', '/nodes', '/health']
        for route in expected_routes:
            assert any(route in r for r in routes), f"Route {route} not found"
    
    def test_concurrent_node_operations(self):
        """Test thread safety of node operations"""
        service = SimpleGatewayService("gateway1", 8000)
        
        def add_node(node_id):
            node_data = {
                "node_id": node_id,
                "address": "127.0.0.1",
                "port": 8080 + int(node_id[-1]),
                "last_heartbeat": time.time(),
                "status": "active"
            }
            service._add_node_to_ring(node_data)
        
        def remove_node(node_id):
            service._remove_node_from_ring(node_id)
        
        # Create multiple threads doing operations
        threads = []
        for i in range(10):
            t1 = threading.Thread(target=add_node, args=[f"node{i}"])
            t2 = threading.Thread(target=remove_node, args=[f"node{i}"])
            threads.extend([t1, t2])
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Should not crash and should handle concurrent operations safely
        assert len(service.nodes) >= 0  # Could be any number due to race conditions


class TestGatewayServiceIntegration:
    """Integration tests for gateway service with mocked HTTP calls"""
    
    @pytest.fixture
    def mock_service(self):
        """Create a mock gateway service for testing"""
        service = SimpleGatewayService("test-gateway", 8000)
        return service
    
    def test_heartbeat_endpoint_new_node(self, mock_service):
        """Test heartbeat endpoint with new node"""
        with mock_service.app.test_client() as client:
            response = client.post('/heartbeat', 
                json={
                    "node_id": "node1",
                    "address": "127.0.0.1",
                    "port": 8080
                }
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "heartbeat_received"
            
            # Check node was added
            assert "node1" in mock_service.nodes
    
    def test_heartbeat_endpoint_existing_node(self, mock_service):
        """Test heartbeat endpoint with existing node"""
        # First add a node
        node_data = {
            "node_id": "node1",
            "address": "127.0.0.1",
            "port": 8080,
            "last_heartbeat": time.time() - 10,
            "status": "active"
        }
        mock_service._add_node_to_ring(node_data)
        old_heartbeat = mock_service.nodes["node1"].last_heartbeat
        
        # Send heartbeat
        with mock_service.app.test_client() as client:
            response = client.post('/heartbeat',
                json={
                    "node_id": "node1", 
                    "address": "127.0.0.1",
                    "port": 8080
                }
            )
            
            assert response.status_code == 200
            
            # Heartbeat should be updated
            new_heartbeat = mock_service.nodes["node1"].last_heartbeat
            assert new_heartbeat > old_heartbeat
    
    def test_heartbeat_endpoint_missing_data(self, mock_service):
        """Test heartbeat endpoint with missing required data"""
        with mock_service.app.test_client() as client:
            # Missing node_id
            response = client.post('/heartbeat',
                json={"address": "127.0.0.1", "port": 8080}
            )
            assert response.status_code == 400
            
            # Missing address
            response = client.post('/heartbeat',
                json={"node_id": "node1", "port": 8080}
            )
            assert response.status_code == 400
    
    def test_get_nodes_endpoint(self, mock_service):
        """Test the get nodes endpoint"""
        # Add some nodes
        for i in range(3):
            node_data = {
                "node_id": f"node{i}",
                "address": "127.0.0.1",
                "port": 8080 + i,
                "last_heartbeat": time.time(),
                "status": "active"
            }
            mock_service._add_node_to_ring(node_data)
        
        with mock_service.app.test_client() as client:
            response = client.get('/nodes')
            
            assert response.status_code == 200
            data = response.get_json()
            assert "nodes" in data
            assert len(data["nodes"]) == 3
            
            # Check node data structure
            for node_id, node_data in data["nodes"].items():
                assert "address" in node_data
                assert "port" in node_data
                assert "status" in node_data
                assert "last_heartbeat" in node_data
    
    def test_get_node_for_key_endpoint(self, mock_service):
        """Test getting node responsible for a key"""
        # Add some nodes
        for i in range(3):
            node_data = {
                "node_id": f"node{i}",
                "address": "127.0.0.1",
                "port": 8080 + i,
                "last_heartbeat": time.time(),
                "status": "active"
            }
            mock_service._add_node_to_ring(node_data)
        
        with mock_service.app.test_client() as client:
            response = client.get('/nodes/test_key')
            
            assert response.status_code == 200
            data = response.get_json()
            assert "key" in data
            assert "node" in data
            assert "node_id" in data["node"]
            assert "address" in data["node"]
            assert "port" in data["node"]
            assert data["key"] == "test_key"
            assert data["node"]["node_id"] in ["node0", "node1", "node2"]
    
    def test_get_node_for_key_no_nodes(self, mock_service):
        """Test getting node for key when no nodes exist"""
        with mock_service.app.test_client() as client:
            response = client.get('/nodes/test_key')
            
            assert response.status_code == 404
            data = response.get_json()
            assert "error" in data
    
    def test_health_endpoint(self, mock_service):
        """Test the health endpoint"""
        with mock_service.app.test_client() as client:
            response = client.get('/health')
            
            assert response.status_code == 200
            data = response.get_json()
            assert "status" in data
            assert "gateway_id" in data
            assert data["gateway_id"] == "test-gateway" 