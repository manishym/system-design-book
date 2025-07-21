"""
Simplified Gateway Service for Consistent Hashing System

This service manages the hash ring, receives heartbeats from KV stores,
and gossips heartbeat information with other gateway instances.
Note: Raft consensus removed for simplicity in testing.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
import uuid

from flask import Flask, request, jsonify
try:
    from .simple_hash_ring import SimpleHashRing
except ImportError:
    from simple_hash_ring import SimpleHashRing
import requests
import threading
from concurrent.futures import ThreadPoolExecutor


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NodeInfo:
    """Information about a KV store node"""
    def __init__(self, node_id: str, address: str, port: int):
        self.node_id = node_id
        self.address = address
        self.port = port
        self.last_heartbeat = time.time()
        self.status = "active"  # active, inactive, dead
        
    def to_dict(self):
        return {
            "node_id": self.node_id,
            "address": self.address,
            "port": self.port,
            "last_heartbeat": self.last_heartbeat,
            "status": self.status
        }
        
    @classmethod
    def from_dict(cls, data):
        node = cls(data["node_id"], data["address"], data["port"])
        node.last_heartbeat = data["last_heartbeat"]
        node.status = data["status"]
        return node


class GossipMessage:
    """Message format for gossip protocol"""
    def __init__(self, message_type: str, sender_id: str, data: dict):
        self.message_id = str(uuid.uuid4())
        self.message_type = message_type  # HEARTBEAT, NODE_UPDATE, RING_SYNC
        self.sender_id = sender_id
        self.data = data
        self.timestamp = time.time()
        
    def to_dict(self):
        return {
            "message_id": self.message_id,
            "message_type": self.message_type,
            "sender_id": self.sender_id,
            "data": self.data,
            "timestamp": self.timestamp
        }
        
    @classmethod
    def from_dict(cls, data):
        msg = cls(data["message_type"], data["sender_id"], data["data"])
        msg.message_id = data["message_id"]
        msg.timestamp = data["timestamp"]
        return msg


class SimpleGatewayService:
    """Simplified Gateway Service class (without Raft)"""
    
    def __init__(self, gateway_id: str, listen_port: int, peer_gateways: List[str] = None):
        self.gateway_id = gateway_id
        self.listen_port = listen_port
        self.peer_gateways = peer_gateways or []
        
        # Hash ring for consistent hashing
        self.hash_ring = SimpleHashRing()
        
        # Node management
        self.nodes: Dict[str, NodeInfo] = {}
        self.node_lock = threading.RLock()
        
        # Gossip protocol
        self.gossip_messages: Set[str] = set()  # Track seen message IDs
        self.gossip_lock = threading.RLock()
        
        # Configuration
        self.heartbeat_timeout = 30  # seconds
        self.gossip_interval = 5     # seconds
        self.health_check_interval = 10  # seconds
        
        # Flask app for HTTP API
        self.app = Flask(__name__)
        self.setup_routes()
        
        # Threading
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.running = False
            
    def _add_node_to_ring(self, node_data: dict) -> bool:
        """Internal method to add node to hash ring"""
        try:
            with self.node_lock:
                node_id = node_data["node_id"]
                if node_id not in self.nodes:
                    node = NodeInfo.from_dict(node_data)
                    self.nodes[node_id] = node
                    
                # Update hash ring
                self.hash_ring.add_node(node_id)
                logger.info(f"Added node {node_id} to hash ring")
                return True
        except Exception as e:
            logger.error(f"Failed to add node to ring: {e}")
            return False
            
    def _remove_node_from_ring(self, node_id: str) -> bool:
        """Internal method to remove node from hash ring"""
        try:
            with self.node_lock:
                if node_id in self.nodes:
                    del self.nodes[node_id]
                    
                # Update hash ring
                self.hash_ring.remove_node(node_id)
                logger.info(f"Removed node {node_id} from hash ring")
                return True
        except Exception as e:
            logger.error(f"Failed to remove node from ring: {e}")
            return False
    
    def setup_routes(self):
        """Setup Flask routes for the gateway API"""
        
        @self.app.route('/heartbeat', methods=['POST'])
        def receive_heartbeat():
            """Receive heartbeat from KV store nodes"""
            try:
                data = request.get_json()
                node_id = data.get('node_id')
                address = data.get('address')
                port = data.get('port', 8080)
                
                if not node_id or not address:
                    return jsonify({"error": "Missing node_id or address"}), 400
                
                # Update or create node info
                with self.node_lock:
                    if node_id not in self.nodes:
                        # New node - add it directly (simplified without Raft)
                        node_data = {
                            "node_id": node_id,
                            "address": address, 
                            "port": port,
                            "last_heartbeat": time.time(),
                            "status": "active"
                        }
                        self._add_node_to_ring(node_data)
                    else:
                        # Existing node - update heartbeat
                        self.nodes[node_id].last_heartbeat = time.time()
                        self.nodes[node_id].status = "active"
                
                # Gossip heartbeat to other gateways
                self._gossip_heartbeat(node_id, address, port)
                
                return jsonify({"status": "heartbeat_received"}), 200
                
            except Exception as e:
                logger.error(f"Error processing heartbeat: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/nodes', methods=['GET'])
        def get_nodes():
            """Get all nodes in the ring"""
            with self.node_lock:
                nodes = {nid: node.to_dict() for nid, node in self.nodes.items()}
            return jsonify({"nodes": nodes}), 200
            
        @self.app.route('/nodes/<key>', methods=['GET'])
        def get_node_for_key(key):
            """Get the node responsible for a given key"""
            try:
                if not self.hash_ring.nodes:
                    return jsonify({"error": "No nodes in ring"}), 404
                    
                node_id = self.hash_ring.get_node(key)
                with self.node_lock:
                    node_info = self.nodes.get(node_id)
                    if node_info:
                        return jsonify({
                            "key": key,
                            "node": node_info.to_dict()
                        }), 200
                    else:
                        return jsonify({"error": "Node not found"}), 404
                        
            except Exception as e:
                logger.error(f"Error getting node for key: {e}")
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/ring/status', methods=['GET'])
        def get_ring_status():
            """Get hash ring status and statistics"""
            with self.node_lock:
                return jsonify({
                    "gateway_id": self.gateway_id,
                    "total_nodes": len(self.nodes),
                    "active_nodes": len([n for n in self.nodes.values() if n.status == "active"]),
                    "ring_nodes": list(self.hash_ring.nodes),
                    "peer_gateways": self.peer_gateways,
                    "simplified": True  # Indicate this is simplified version
                }), 200
                
        @self.app.route('/gossip', methods=['POST'])
        def receive_gossip():
            """Receive gossip messages from other gateways"""
            try:
                data = request.get_json()
                message = GossipMessage.from_dict(data)
                
                # Process gossip message
                self._process_gossip_message(message)
                
                return jsonify({"status": "gossip_received"}), 200
                
            except Exception as e:
                logger.error(f"Error processing gossip: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint"""
            with self.node_lock:
                return jsonify({
                    "status": "healthy",
                    "gateway_id": self.gateway_id,
                    "nodes_count": len(self.nodes),
                    "active_nodes": len([n for n in self.nodes.values() if n.status == "active"]),
                    "timestamp": time.time()
                }), 200
                    
        @self.app.route('/admin/clear_nodes', methods=['POST'])
        def clear_nodes():
            """Clear all registered nodes (for testing)"""
            with self.node_lock:
                cleared_count = len(self.nodes)
                self.nodes.clear()
                self.hash_ring = SimpleHashRing(virtual_nodes=100)  # Use default virtual nodes count
                logger.info(f"Cleared {cleared_count} nodes from gateway {self.gateway_id}")
                return jsonify({
                    "status": "success",
                    "cleared_nodes": cleared_count,
                    "gateway_id": self.gateway_id
                }), 200
    
    def _check_node_health(self):
        """Check health of all nodes and update their status"""
        current_time = time.time()
        dead_nodes = []
        
        with self.node_lock:
            logger.info(f"Health check running for {len(self.nodes)} nodes")
            for node_id, node in self.nodes.items():
                time_since_heartbeat = current_time - node.last_heartbeat
                logger.debug(f"Node {node_id}: last heartbeat {time_since_heartbeat:.1f}s ago, status: {node.status}")
                
                # Check if node has sent heartbeat recently
                if time_since_heartbeat > self.heartbeat_timeout:
                    if node.status != "dead":
                        logger.warning(f"Node {node_id} heartbeat timeout ({time_since_heartbeat:.1f}s > {self.heartbeat_timeout}s)")
                        node.status = "dead"
                        dead_nodes.append(node_id)
                    continue
                    
                # Try to ping the node if heartbeat is still recent
                try:
                    health_url = f"http://{node.address}:{node.port}/health"
                    logger.debug(f"Checking health of {node_id} at {health_url}")
                    response = requests.get(health_url, timeout=3)
                    if response.status_code == 200:
                        if node.status != "active":
                            logger.info(f"Node {node_id} health check passed - marking as active")
                        node.status = "active"
                    else:
                        if node.status != "dead":
                            logger.warning(f"Node {node_id} health check failed with status {response.status_code}")
                            node.status = "dead"
                            dead_nodes.append(node_id)
                except Exception as e:
                    if node.status != "dead":
                        logger.warning(f"Node {node_id} health check failed: {e}")
                        node.status = "dead"
                        dead_nodes.append(node_id)
        
        # Remove dead nodes from ring (simplified without Raft)
        if dead_nodes:
            logger.info(f"Removing {len(dead_nodes)} dead nodes: {dead_nodes}")
        for node_id in dead_nodes:
            self._remove_node_from_ring(node_id)
    
    def _gossip_heartbeat(self, node_id: str, address: str, port: int):
        """Send heartbeat gossip to other gateways"""
        message = GossipMessage(
            message_type="HEARTBEAT",
            sender_id=self.gateway_id,
            data={
                "node_id": node_id,
                "address": address,
                "port": port,
                "timestamp": time.time()
            }
        )
        self._send_gossip_to_peers(message)
        
    def _send_gossip_to_peers(self, message: GossipMessage):
        """Send gossip message to all peer gateways"""
        for peer in self.peer_gateways:
            self.executor.submit(self._send_gossip_to_peer, peer, message)
            
    def _send_gossip_to_peer(self, peer_address: str, message: GossipMessage):
        """Send gossip message to a specific peer"""
        try:
            response = requests.post(
                f"http://{peer_address}/gossip",
                json=message.to_dict(),
                timeout=5
            )
            if response.status_code == 200:
                logger.debug(f"Gossip sent to {peer_address}")
            else:
                logger.warning(f"Gossip failed to {peer_address}: {response.status_code}")
        except Exception as e:
            logger.warning(f"Failed to send gossip to {peer_address}: {e}")
            
    def _process_gossip_message(self, message: GossipMessage):
        """Process received gossip message"""
        with self.gossip_lock:
            # Avoid processing duplicate messages
            if message.message_id in self.gossip_messages:
                return
            self.gossip_messages.add(message.message_id)
            
        logger.info(f"Processing gossip: {message.message_type} from {message.sender_id}")
        
        if message.message_type == "HEARTBEAT":
            # Update node heartbeat info
            data = message.data
            node_id = data["node_id"]
            
            with self.node_lock:
                if node_id in self.nodes:
                    self.nodes[node_id].last_heartbeat = data["timestamp"]
                    self.nodes[node_id].status = "active"
        
        # Propagate gossip to other peers (with hop limit to prevent loops)
        if message.sender_id != self.gateway_id:
            self._send_gossip_to_peers(message)
    
    def _health_check_loop(self):
        """Background task to check node health and remove dead nodes"""
        while self.running:
            try:
                self._check_node_health()
                    
            except Exception as e:
                logger.error(f"Health check error: {e}")
                
            time.sleep(self.health_check_interval)
    
    def start(self):
        """Start the gateway service"""
        self.running = True
        
        # Start health check thread
        health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        health_thread.start()
        
        logger.info(f"Starting Simplified Gateway Service {self.gateway_id} on port {self.listen_port}")
        
        # Start Flask app
        self.app.run(host='0.0.0.0', port=self.listen_port, threaded=True)
        
    def stop(self):
        """Stop the gateway service"""
        self.running = False
        logger.info("Gateway service stopped")


def main():
    """Main function to run gateway service"""
    import argparse
    import os
    
    # Use environment variables if available, otherwise use command line args
    gateway_id = os.getenv('GATEWAY_ID')
    listen_port = int(os.getenv('LISTEN_PORT', '8000'))
    peer_gateways_str = os.getenv('PEER_GATEWAYS', '')
    peer_gateways = peer_gateways_str.split() if peer_gateways_str else []
    
    # If environment variables are not set, parse command line arguments
    if not gateway_id:
        parser = argparse.ArgumentParser(description='Simplified Gateway Service for Consistent Hashing')
        parser.add_argument('--gateway-id', required=True, help='Unique gateway ID')
        parser.add_argument('--port', type=int, default=8000, help='HTTP port to listen on')
        parser.add_argument('--peers', nargs='*', default=[], help='Peer gateway addresses')
        
        args = parser.parse_args()
        gateway_id = args.gateway_id
        listen_port = args.port
        peer_gateways = args.peers
    
    gateway = SimpleGatewayService(
        gateway_id=gateway_id,
        listen_port=listen_port,
        peer_gateways=peer_gateways
    )
    
    try:
        gateway.start()
    except KeyboardInterrupt:
        gateway.stop()


if __name__ == "__main__":
    main() 