"""
Unit tests for SimpleHashRing implementation
"""

import pytest
from collections import defaultdict, Counter
from gateway.simple_hash_ring import SimpleHashRing


class TestSimpleHashRing:
    """Test cases for SimpleHashRing class"""
    
    def test_empty_ring_initialization(self):
        """Test that empty ring is properly initialized"""
        ring = SimpleHashRing()
        assert len(ring.nodes) == 0
        assert len(ring.ring) == 0
        assert len(ring.sorted_keys) == 0
        assert ring.get_node("any_key") is None
    
    def test_virtual_nodes_configuration(self):
        """Test ring initialization with different virtual node counts"""
        # Default virtual nodes
        ring1 = SimpleHashRing()
        assert ring1.virtual_nodes == 150
        
        # Custom virtual nodes
        ring2 = SimpleHashRing(virtual_nodes=50)
        assert ring2.virtual_nodes == 50
    
    def test_add_single_node(self):
        """Test adding a single node to the ring"""
        ring = SimpleHashRing(virtual_nodes=10)
        
        ring.add_node("node1")
        
        assert "node1" in ring.nodes
        assert len(ring.ring) == 10  # Should have 10 virtual nodes
        assert len(ring.sorted_keys) == 10
        assert all(ring.ring[key] == "node1" for key in ring.sorted_keys)
    
    def test_add_multiple_nodes(self):
        """Test adding multiple nodes to the ring"""
        ring = SimpleHashRing(virtual_nodes=5)
        
        nodes = ["node1", "node2", "node3"]
        for node in nodes:
            ring.add_node(node)
        
        assert len(ring.nodes) == 3
        assert len(ring.ring) == 15  # 3 nodes * 5 virtual nodes each
        assert len(ring.sorted_keys) == 15
        
        # Verify all nodes are represented
        ring_nodes = set(ring.ring.values())
        assert ring_nodes == set(nodes)
    
    def test_add_duplicate_node(self):
        """Test that adding the same node twice has no effect"""
        ring = SimpleHashRing(virtual_nodes=5)
        
        ring.add_node("node1")
        original_size = len(ring.ring)
        
        # Adding same node again should not change anything
        ring.add_node("node1")
        
        assert len(ring.ring) == original_size
        assert len(ring.nodes) == 1
    
    def test_remove_node(self):
        """Test removing a node from the ring"""
        ring = SimpleHashRing(virtual_nodes=5)
        
        ring.add_node("node1")
        ring.add_node("node2")
        
        assert len(ring.ring) == 10
        
        ring.remove_node("node1")
        
        assert "node1" not in ring.nodes
        assert len(ring.ring) == 5  # Only node2's virtual nodes remain
        assert all(ring.ring[key] == "node2" for key in ring.sorted_keys)
    
    def test_remove_nonexistent_node(self):
        """Test removing a node that doesn't exist"""
        ring = SimpleHashRing(virtual_nodes=5)
        
        ring.add_node("node1")
        original_size = len(ring.ring)
        
        # Removing non-existent node should not change anything
        ring.remove_node("node2")
        
        assert len(ring.ring) == original_size
        assert len(ring.nodes) == 1
    
    def test_get_node_for_key(self):
        """Test getting the responsible node for a key"""
        ring = SimpleHashRing(virtual_nodes=10)
        
        ring.add_node("node1")
        ring.add_node("node2")
        ring.add_node("node3")
        
        # Test with various keys
        test_keys = ["user:123", "product:abc", "order:456", "session:xyz"]
        
        for key in test_keys:
            node = ring.get_node(key)
            assert node in ["node1", "node2", "node3"]
            
            # Same key should always return the same node
            assert ring.get_node(key) == node
    
    def test_consistent_hashing_property(self):
        """Test that the hash ring maintains consistency"""
        ring = SimpleHashRing(virtual_nodes=20)
        
        # Add initial nodes
        ring.add_node("node1")
        ring.add_node("node2")
        ring.add_node("node3")
        
        # Test a set of keys
        test_keys = [f"key_{i}" for i in range(100)]
        initial_mapping = {key: ring.get_node(key) for key in test_keys}
        
        # Add a new node
        ring.add_node("node4")
        
        # Check how many keys were remapped
        remapped_count = 0
        for key in test_keys:
            if ring.get_node(key) != initial_mapping[key]:
                remapped_count += 1
        
        # Should only remap a fraction of keys (consistent hashing property)
        # With good hash function, typically < 30% get remapped when adding 1 node to 3
        assert remapped_count < len(test_keys) * 0.5
    
    def test_key_distribution(self):
        """Test that keys are reasonably distributed across nodes"""
        ring = SimpleHashRing(virtual_nodes=50)
        
        nodes = ["node1", "node2", "node3", "node4"]
        for node in nodes:
            ring.add_node(node)
        
        # Test with many keys
        test_keys = [f"key_{i}" for i in range(1000)]
        distribution = defaultdict(int)
        
        for key in test_keys:
            node = ring.get_node(key)
            distribution[node] += 1
        
        # Check that each node gets some keys (roughly balanced)
        for node in nodes:
            assert distribution[node] > 0
            # Each node should get roughly 1/4 of keys (allowing for variance)
            assert 150 < distribution[node] < 350  # 25% ± 10%
    
    def test_get_multiple_nodes(self):
        """Test getting multiple nodes for replication"""
        ring = SimpleHashRing(virtual_nodes=10)
        
        nodes = ["node1", "node2", "node3", "node4"]
        for node in nodes:
            ring.add_node(node)
        
        # Test getting multiple nodes for a key
        key = "test_key"
        
        # Test different replication factors
        nodes_1 = ring.get_nodes(key, count=1)
        nodes_2 = ring.get_nodes(key, count=2)
        nodes_3 = ring.get_nodes(key, count=3)
        nodes_all = ring.get_nodes(key, count=10)  # More than available
        
        assert len(nodes_1) == 1
        assert len(nodes_2) == 2
        assert len(nodes_3) == 3
        assert len(nodes_all) == 4  # Should return all available nodes
        
        # First node should be the same as single get_node
        assert nodes_1[0] == ring.get_node(key)
        
        # All returned nodes should be unique
        assert len(set(nodes_2)) == 2
        assert len(set(nodes_3)) == 3
        assert len(set(nodes_all)) == 4
        
        # Check order consistency
        assert nodes_2[0] == nodes_1[0]
        assert nodes_3[:2] == nodes_2
    
    def test_get_nodes_edge_cases(self):
        """Test edge cases for get_nodes method"""
        ring = SimpleHashRing(virtual_nodes=5)
        
        # Empty ring
        assert ring.get_nodes("key", count=1) == []
        assert ring.get_nodes("key", count=0) == []
        
        # Single node
        ring.add_node("node1")
        assert ring.get_nodes("key", count=1) == ["node1"]
        assert ring.get_nodes("key", count=5) == ["node1"]  # Can't return more than available
        
        # Zero count
        assert ring.get_nodes("key", count=0) == []
        
        # Negative count
        assert ring.get_nodes("key", count=-1) == []
    
    def test_hash_function_consistency(self):
        """Test that the hash function is consistent"""
        ring = SimpleHashRing()
        
        # Same input should always produce same hash
        key = "test_key"
        hash1 = ring._hash(key)
        hash2 = ring._hash(key)
        
        assert hash1 == hash2
        assert isinstance(hash1, int)
        assert hash1 >= 0
    
    def test_ring_ordering(self):
        """Test that ring keys are properly sorted"""
        ring = SimpleHashRing(virtual_nodes=10)
        
        ring.add_node("node1")
        ring.add_node("node2")
        
        # Check that sorted_keys is indeed sorted
        assert ring.sorted_keys == sorted(ring.sorted_keys)
        
        # Check that all ring keys are in sorted_keys
        assert set(ring.sorted_keys) == set(ring.ring.keys())
    
    def test_node_removal_preserves_consistency(self):
        """Test that removing nodes doesn't break consistency for remaining keys"""
        ring = SimpleHashRing(virtual_nodes=20)
        
        # Add nodes
        nodes = ["node1", "node2", "node3", "node4"]
        for node in nodes:
            ring.add_node(node)
        
        # Get initial mapping
        test_keys = [f"key_{i}" for i in range(100)]
        initial_mapping = {key: ring.get_node(key) for key in test_keys}
        
        # Remove a node
        ring.remove_node("node2")
        
        # Keys that were on remaining nodes should stay on the same nodes
        # (only keys that were on node2 should be remapped)
        for key in test_keys:
            if initial_mapping[key] != "node2":
                # Keys not on removed node should stay on same node
                assert ring.get_node(key) == initial_mapping[key]
    
    def test_clockwise_node_selection(self):
        """Test that nodes are selected in clockwise manner"""
        ring = SimpleHashRing(virtual_nodes=1)  # Minimal virtual nodes for predictability
        
        # Add nodes in specific order
        ring.add_node("node1")
        ring.add_node("node2")
        
        # Test many keys to ensure clockwise selection
        for i in range(100):
            key = f"test_key_{i}"
            node = ring.get_node(key)
            
            # Should get a valid node
            assert node in ["node1", "node2"]
            
            # Same key should always return same node
            assert ring.get_node(key) == node
    
    @pytest.mark.parametrize("virtual_nodes", [1, 10, 50, 100, 200])
    def test_different_virtual_node_counts(self, virtual_nodes):
        """Test ring behavior with different virtual node counts"""
        ring = SimpleHashRing(virtual_nodes=virtual_nodes)
        
        # Add some nodes
        nodes = ["node1", "node2", "node3"]
        for node in nodes:
            ring.add_node(node)
        
        # Verify virtual node count
        assert len(ring.ring) == len(nodes) * virtual_nodes
        
        # Test key assignment
        test_key = "test_key"
        assigned_node = ring.get_node(test_key)
        assert assigned_node in nodes
        
        # Test multiple node retrieval
        multi_nodes = ring.get_nodes(test_key, count=2)
        assert len(multi_nodes) == 2
        assert all(node in nodes for node in multi_nodes) 