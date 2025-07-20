"""
KV Store Service for Consistent Hashing System

This service provides a key-value store that registers with the gateway
and sends periodic heartbeats to maintain liveness.
"""

import asyncio
import json
import logging
import time
import threading
from typing import Dict, Any, Optional
import uuid

import requests
from flask import Flask, request, jsonify


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KVStoreService:
    """Key-Value Store Service that integrates with Gateway"""
    
    def __init__(self, node_id: str, listen_port: int, gateway_address: str):
        self.node_id = node_id
        self.listen_port = listen_port
        self.gateway_address = gateway_address
        self.listen_address = "0.0.0.0"
        
        # In-memory key-value store
        self.data: Dict[str, Any] = {}
        self.data_lock = threading.RLock()
        
        # Configuration
        self.heartbeat_interval = 10  # seconds
        self.registration_retry_interval = 5  # seconds
        
        # Flask app for HTTP API
        self.app = Flask(__name__)
        self.setup_routes()
        
        # Service state
        self.running = False
        self.registered = False
        
    def setup_routes(self):
        """Setup Flask routes for the KV store API"""
        
        @self.app.route('/put', methods=['POST'])
        def put_key():
            """Store a key-value pair"""
            try:
                data = request.get_json()
                key = data.get('key')
                value = data.get('value')
                
                if not key:
                    return jsonify({"error": "Missing key"}), 400
                    
                with self.data_lock:
                    self.data[key] = value
                    
                logger.info(f"Stored key: {key}")
                return jsonify({
                    "status": "stored",
                    "key": key,
                    "node_id": self.node_id
                }), 200
                
            except Exception as e:
                logger.error(f"Error storing key: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/get/<key>', methods=['GET'])
        def get_key(key):
            """Retrieve a value by key"""
            try:
                with self.data_lock:
                    if key in self.data:
                        return jsonify({
                            "key": key,
                            "value": self.data[key],
                            "node_id": self.node_id
                        }), 200
                    else:
                        return jsonify({"error": "Key not found"}), 404
                        
            except Exception as e:
                logger.error(f"Error retrieving key: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/get', methods=['POST'])
        def get_key_by_body():
            """Retrieve a value by key (key in POST body for special characters)"""
            try:
                data = request.get_json()
                key = data.get('key')
                
                if not key:
                    return jsonify({"error": "Missing key"}), 400
                
                with self.data_lock:
                    if key in self.data:
                        return jsonify({
                            "key": key,
                            "value": self.data[key],
                            "node_id": self.node_id
                        }), 200
                    else:
                        return jsonify({"error": "Key not found"}), 404
                        
            except Exception as e:
                logger.error(f"Error retrieving key: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/delete/<key>', methods=['DELETE'])
        def delete_key(key):
            """Delete a key-value pair"""
            try:
                with self.data_lock:
                    if key in self.data:
                        del self.data[key]
                        return jsonify({
                            "status": "deleted",
                            "key": key,
                            "node_id": self.node_id
                        }), 200
                    else:
                        return jsonify({"error": "Key not found"}), 404
                        
            except Exception as e:
                logger.error(f"Error deleting key: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/delete', methods=['POST'])
        def delete_key_by_body():
            """Delete a key-value pair (key in POST body for special characters)"""
            try:
                data = request.get_json()
                key = data.get('key')
                
                if not key:
                    return jsonify({"error": "Missing key"}), 400
                
                with self.data_lock:
                    if key in self.data:
                        del self.data[key]
                        return jsonify({
                            "status": "deleted",
                            "key": key,
                            "node_id": self.node_id
                        }), 200
                    else:
                        return jsonify({"error": "Key not found"}), 404
                        
            except Exception as e:
                logger.error(f"Error deleting key: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/keys', methods=['GET'])
        def list_keys():
            """List all keys in this store"""
            try:
                with self.data_lock:
                    keys = list(self.data.keys())
                    
                return jsonify({
                    "keys": keys,
                    "count": len(keys),
                    "node_id": self.node_id
                }), 200
                
            except Exception as e:
                logger.error(f"Error listing keys: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint"""
            # Only return 503 if explicitly stopped (not just not started yet)
            if hasattr(self, '_explicitly_stopped') and self._explicitly_stopped:
                return jsonify({"status": "stopping"}), 503
            return jsonify({
                "status": "healthy",
                "node_id": self.node_id,
                "registered": self.registered,
                "key_count": len(self.data)
            }), 200
            
        @self.app.route('/admin/shutdown', methods=['POST'])
        def shutdown():
            """Shutdown endpoint for graceful shutdown"""
            func = request.environ.get('werkzeug.server.shutdown')
            if func is None:
                return 'Not running with the Werkzeug Server', 500
            func()
            return 'Server shutting down...', 200
        
        @self.app.route('/stats', methods=['GET'])
        def get_stats():
            """Get node statistics"""
            with self.data_lock:
                return jsonify({
                    "node_id": self.node_id,
                    "address": f"{self.listen_address}:{self.listen_port}",
                    "key_count": len(self.data),
                    "registered": self.registered,
                    "gateway": self.gateway_address,
                    "uptime": time.time() - self.start_time if hasattr(self, 'start_time') else 0
                }), 200
    
    def _register_with_gateway(self) -> bool:
        """Register this KV store with the gateway"""
        try:
            heartbeat_data = {
                "node_id": self.node_id,
                "address": self.listen_address,
                "port": self.listen_port
            }
            
            response = requests.post(
                f"http://{self.gateway_address}/heartbeat",
                json=heartbeat_data,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Successfully registered with gateway {self.gateway_address}")
                self.registered = True
                return True
            else:
                logger.error(f"Registration failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to register with gateway: {e}")
            return False
    
    def _send_heartbeat(self) -> bool:
        """Send heartbeat to gateway"""
        try:
            heartbeat_data = {
                "node_id": self.node_id,
                "address": self.listen_address,
                "port": self.listen_port,
                "timestamp": time.time(),
                "key_count": len(self.data)
            }
            
            response = requests.post(
                f"http://{self.gateway_address}/heartbeat",
                json=heartbeat_data,
                timeout=5
            )
            
            if response.status_code == 200:
                logger.debug(f"Heartbeat sent successfully")
                return True
            else:
                logger.warning(f"Heartbeat failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.warning(f"Failed to send heartbeat: {e}")
            return False
    
    def _heartbeat_loop(self):
        """Background task to send periodic heartbeats"""
        while self.running:
            try:
                if not self.registered:
                    # Try to register first
                    if self._register_with_gateway():
                        self.registered = True
                    else:
                        time.sleep(self.registration_retry_interval)
                        continue
                
                # Send heartbeat
                if not self._send_heartbeat():
                    # If heartbeat fails, mark as unregistered to retry registration
                    self.registered = False
                    logger.warning("Heartbeat failed, will retry registration")
                    
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                self.registered = False
                
            time.sleep(self.heartbeat_interval)
    
    def start(self):
        """Start the KV store service"""
        self.running = True
        self.start_time = time.time()
        
        # Start heartbeat thread
        heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        heartbeat_thread.start()
        
        logger.info(f"Starting KV Store Service {self.node_id} on port {self.listen_port}")
        logger.info(f"Will register with gateway at {self.gateway_address}")
        
        # Start Flask app
        self.app.run(host=self.listen_address, port=self.listen_port, threaded=True)
        
    def stop(self):
        """Stop the KV store service"""
        self.running = False
        self.registered = False
        self._explicitly_stopped = True  # Mark as explicitly stopped for health checks
        
        # Try to shutdown Flask server gracefully
        try:
            import requests
            requests.post(f"http://{self.listen_address}:{self.listen_port}/admin/shutdown", timeout=1)
        except:
            # If graceful shutdown fails, that's okay - server will stop responding to health checks
            pass
            
        logger.info("KV Store service stopped")


class KVStoreClient:
    """Client for interacting with KV store nodes"""
    
    def __init__(self, gateway_address: str):
        self.gateway_address = gateway_address
        
    def put(self, key: str, value: Any) -> bool:
        """Store a key-value pair using consistent hashing"""
        try:
            # Get the responsible node from gateway
            response = requests.get(f"http://{self.gateway_address}/nodes/{key}")
            if response.status_code != 200:
                logger.error(f"Failed to get node for key {key}")
                return False
                
            node_info = response.json()["node"]
            node_address = f"{node_info['address']}:{node_info['port']}"
            
            # Store the key-value pair in the responsible node
            store_response = requests.post(
                f"http://{node_address}/put",
                json={"key": key, "value": value},
                timeout=5
            )
            
            return store_response.status_code == 200
            
        except Exception as e:
            logger.error(f"Failed to put key {key}: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value by key using consistent hashing"""
        try:
            # Get the responsible node from gateway
            response = requests.get(f"http://{self.gateway_address}/nodes/{key}")
            if response.status_code != 200:
                logger.error(f"Failed to get node for key {key}")
                return None
                
            node_info = response.json()["node"]
            node_address = f"{node_info['address']}:{node_info['port']}"
            
            # Try POST method first (handles special characters)
            try:
                get_response = requests.post(
                    f"http://{node_address}/get",
                    json={"key": key},
                    timeout=5
                )
                if get_response.status_code == 200:
                    return get_response.json()["value"]
            except:
                pass
            
            # Fallback to GET method (for backward compatibility)
            try:
                get_response = requests.get(f"http://{node_address}/get/{key}", timeout=5)
                if get_response.status_code == 200:
                    return get_response.json()["value"]
            except:
                pass
                
            return None
                
        except Exception as e:
            logger.error(f"Failed to get key {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete a key using consistent hashing"""
        try:
            # Get the responsible node from gateway
            response = requests.get(f"http://{self.gateway_address}/nodes/{key}")
            if response.status_code != 200:
                logger.error(f"Failed to get node for key {key}")
                return False
                
            node_info = response.json()["node"]
            node_address = f"{node_info['address']}:{node_info['port']}"
            
            # Try POST method first (handles special characters)
            try:
                delete_response = requests.post(
                    f"http://{node_address}/delete",
                    json={"key": key},
                    timeout=5
                )
                if delete_response.status_code == 200:
                    return True
            except:
                pass
            
            # Fallback to DELETE method (for backward compatibility)
            try:
                delete_response = requests.delete(f"http://{node_address}/delete/{key}", timeout=5)
                return delete_response.status_code == 200
            except:
                return False
            
        except Exception as e:
            logger.error(f"Failed to delete key {key}: {e}")
            return False


def main():
    """Main function to run KV store service"""
    import argparse
    import os
    
    # Use environment variables if available, otherwise use command line args
    node_id = os.getenv('NODE_ID')
    listen_port = int(os.getenv('LISTEN_PORT', '8080'))
    gateway_address = os.getenv('GATEWAY_ADDRESS')
    
    # If environment variables are not set, parse command line arguments
    if not node_id or not gateway_address:
        parser = argparse.ArgumentParser(description='KV Store Service for Consistent Hashing')
        parser.add_argument('--node-id', required=True, help='Unique node ID')
        parser.add_argument('--port', type=int, default=8080, help='HTTP port to listen on')
        parser.add_argument('--gateway', required=True, help='Gateway address (host:port)')
        
        args = parser.parse_args()
        node_id = args.node_id
        listen_port = args.port
        gateway_address = args.gateway
    
    kvstore = KVStoreService(
        node_id=node_id,
        listen_port=listen_port,
        gateway_address=gateway_address
    )
    
    try:
        kvstore.start()
    except KeyboardInterrupt:
        kvstore.stop()


if __name__ == "__main__":
    main() 