"""
Simple Hash Ring Implementation for Consistent Hashing

A basic implementation of consistent hashing for the gateway service.
"""

import hashlib
from typing import List, Optional


class SimpleHashRing:
    """Simple implementation of a consistent hash ring"""
    
    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self.ring = {}  # hash -> node_id
        self.sorted_keys = []
        self.nodes = set()
        
    def _hash(self, key: str) -> int:
        """Generate hash for a key"""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def add_node(self, node_id: str):
        """Add a node to the ring"""
        if node_id in self.nodes:
            return
            
        self.nodes.add(node_id)
        
        # Add virtual nodes
        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:{i}"
            hash_val = self._hash(virtual_key)
            self.ring[hash_val] = node_id
            
        # Keep sorted keys for binary search
        self.sorted_keys = sorted(self.ring.keys())
        
    def remove_node(self, node_id: str):
        """Remove a node from the ring"""
        if node_id not in self.nodes:
            return
            
        self.nodes.remove(node_id)
        
        # Remove virtual nodes
        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:{i}"
            hash_val = self._hash(virtual_key)
            if hash_val in self.ring:
                del self.ring[hash_val]
                
        # Update sorted keys
        self.sorted_keys = sorted(self.ring.keys())
        
    def get_node(self, key: str) -> Optional[str]:
        """Get the node responsible for a key"""
        if not self.ring:
            return None
            
        hash_val = self._hash(key)
        
        # Find the first node clockwise from the hash
        for ring_key in self.sorted_keys:
            if ring_key >= hash_val:
                return self.ring[ring_key]
                
        # Wrap around to the first node
        return self.ring[self.sorted_keys[0]]
        
    def get_nodes(self, key: str, count: int = 1) -> List[str]:
        """Get multiple nodes for a key (for replication)"""
        if not self.ring or count <= 0:
            return []
            
        hash_val = self._hash(key)
        result = []
        seen_nodes = set()
        
        # Start from the position of the key
        start_idx = 0
        for i, ring_key in enumerate(self.sorted_keys):
            if ring_key >= hash_val:
                start_idx = i
                break
                
        # Collect unique nodes
        for i in range(len(self.sorted_keys)):
            idx = (start_idx + i) % len(self.sorted_keys)
            node = self.ring[self.sorted_keys[idx]]
            
            if node not in seen_nodes:
                result.append(node)
                seen_nodes.add(node)
                
                if len(result) >= count:
                    break
                    
        return result 