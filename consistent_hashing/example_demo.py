#!/usr/bin/env python3
"""
Demo script for Consistent Hashing System

This script demonstrates how to:
1. Start multiple gateway services
2. Start multiple KV store services  
3. Use the KV store client to interact with the system
4. Show consistent hashing in action
"""

import subprocess
import time
import requests
import json
import signal
import sys
from typing import List, Optional, Any

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'storage', 'kvstore'))
from kvstore_service import KVStoreClient


class ProcessManager:
    """Manages multiple processes for the demo"""
    
    def __init__(self):
        self.processes: List[subprocess.Popen[bytes]] = []
        
    def start_gateway(self, gateway_id: str, port: int, raft_port: int, peers: Optional[List[str]] = None):
        """Start a gateway service"""
        cmd = [
            "python", "gateway/gateway_service.py",
            "--gateway-id", gateway_id,
            "--port", str(port),
            "--raft-port", str(raft_port)
        ]
        
        if peers:
            cmd.extend(["--peers"] + peers)
            
        print(f"Starting gateway {gateway_id} on port {port}")
        process = subprocess.Popen(cmd)
        self.processes.append(process)
        return process
        
    def start_kvstore(self, node_id: str, port: int, gateway: str):
        """Start a KV store service"""
        cmd = [
            "python", "storage/kvstore/kvstore_service.py",
            "--node-id", node_id,
            "--port", str(port),
            "--gateway", gateway
        ]
        
        print(f"Starting KV store {node_id} on port {port}")
        process = subprocess.Popen(cmd)
        self.processes.append(process)
        return process
        
    def stop_all(self):
        """Stop all managed processes"""
        print("Stopping all processes...")
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        self.processes.clear()


def wait_for_service(url: str, timeout: int = 30) -> bool:
    """Wait for a service to become available"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False


def demo_basic_operations(client: KVStoreClient):
    """Demonstrate basic KV operations"""
    print("\n=== Basic Operations Demo ===")
    
    test_data = {
        "user:1001": {"name": "Alice", "age": 25},
        "user:1002": {"name": "Bob", "age": 30}, 
        "user:1003": {"name": "Charlie", "age": 28},
        "product:2001": {"name": "Laptop", "price": 999.99},
        "product:2002": {"name": "Mouse", "price": 29.99},
        "order:3001": {"user_id": 1001, "product_id": 2001, "quantity": 1}
    }
    
    # Store data
    print("Storing data...")
    for key, value in test_data.items():
        success = client.put(key, value)
        print(f"  PUT {key}: {'✓' if success else '✗'}")
        
    time.sleep(2)
    
    # Retrieve data
    print("\nRetrieving data...")
    for key in test_data.keys():
        value = client.get(key)
        print(f"  GET {key}: {value}")
        
    # Delete some data
    print("\nDeleting data...")
    delete_keys = ["user:1002", "product:2002"]
    for key in delete_keys:
        success = client.delete(key)
        print(f"  DELETE {key}: {'✓' if success else '✗'}")
        
    # Verify deletions
    print("\nVerifying deletions...")
    for key in delete_keys:
        value = client.get(key)
        print(f"  GET {key}: {value}")


def demo_consistent_hashing(gateway_address: str):
    """Demonstrate consistent hashing behavior"""
    print("\n=== Consistent Hashing Demo ===")
    
    # Show current ring status
    try:
        response = requests.get(f"http://{gateway_address}/ring/status")
        if response.status_code == 200:
            ring_info = response.json()
            print(f"Ring Status: {json.dumps(ring_info, indent=2)}")
        
        # Show which node handles different keys
        test_keys = ["user:1001", "user:1002", "product:2001", "order:3001", "cache:abc", "session:xyz"]
        print("\nKey distribution:")
        for key in test_keys:
            response = requests.get(f"http://{gateway_address}/nodes/{key}")
            if response.status_code == 200:
                node_info = response.json()
                node_id = node_info["node"]["node_id"]
                print(f"  {key} -> {node_id}")
            else:
                print(f"  {key} -> No nodes available")
                
    except Exception as e:
        print(f"Error querying ring: {e}")


def demo_node_failure_recovery(manager: ProcessManager, gateway_address: str):
    """Demonstrate node failure and recovery"""
    print("\n=== Node Failure and Recovery Demo ===")
    
    client = KVStoreClient(gateway_address)
    
    # Store some test data
    test_keys = ["test:fail1", "test:fail2", "test:fail3"]
    for key in test_keys:
        client.put(key, f"value_{key}")
    
    print("Stored test data")
    time.sleep(5)
    
    # Show initial distribution
    print("Initial key distribution:")
    for key in test_keys:
        try:
            response = requests.get(f"http://{gateway_address}/nodes/{key}")
            if response.status_code == 200:
                node_id = response.json()["node"]["node_id"]
                print(f"  {key} -> {node_id}")
        except:
            print(f"  {key} -> Error")
    
    # Simulate node failure by stopping one KV store
    print("\nSimulating node failure (stopping one process)...")
    if manager.processes:
        # Stop the last started process (likely a KV store)
        failed_process = manager.processes.pop()
        failed_process.terminate()
        try:
            failed_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            failed_process.kill()
    
    # Wait for failure detection
    print("Waiting for failure detection...")
    time.sleep(35)  # Wait longer than heartbeat timeout
    
    # Show ring status after failure
    try:
        response = requests.get(f"http://{gateway_address}/ring/status")
        if response.status_code == 200:
            ring_info = response.json()
            print(f"Ring Status after failure: {json.dumps(ring_info, indent=2)}")
    except Exception as e:
        print(f"Error querying ring: {e}")
    
    # Show redistribution
    print("Key distribution after failure:")
    for key in test_keys:
        try:
            response = requests.get(f"http://{gateway_address}/nodes/{key}")
            if response.status_code == 200:
                node_id = response.json()["node"]["node_id"]
                print(f"  {key} -> {node_id}")
        except:
            print(f"  {key} -> Error")


def main():
    """Main demo function"""
    manager = ProcessManager()
    
    # Signal handler for clean shutdown
    def signal_handler(sig: Any, frame: Any) -> None:
        print("\nShutting down demo...")
        manager.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        print("=== Consistent Hashing System Demo ===")
        
        # Start gateway services
        gateway_peers = ["localhost:8001", "localhost:8002", "localhost:8003"]
        manager.start_gateway("gateway-1", 8000, 8001, gateway_peers[1:])
        manager.start_gateway("gateway-2", 8001, 8002, [gateway_peers[0], gateway_peers[2]])
        manager.start_gateway("gateway-3", 8002, 8003, gateway_peers[:2])
        
        # Wait for gateways to start
        print("Waiting for gateways to start...")
        time.sleep(5)
        
        # Check if gateways are running
        for i, port in enumerate([8000, 8001, 8002]):
            if wait_for_service(f"http://localhost:{port}/ring/status", 10):
                print(f"Gateway {i+1} is ready")
            else:
                print(f"Gateway {i+1} failed to start")
        
        # Start KV store services
        gateway_address = "localhost:8000"  # Use first gateway
        manager.start_kvstore("kvstore-A", 8080, gateway_address)
        manager.start_kvstore("kvstore-B", 8081, gateway_address) 
        manager.start_kvstore("kvstore-C", 8082, gateway_address)
        
        # Wait for KV stores to register
        print("Waiting for KV stores to register...")
        time.sleep(15)
        
        # Create client
        client = KVStoreClient(gateway_address)
        
        # Run demos
        demo_basic_operations(client)
        demo_consistent_hashing(gateway_address)
        demo_node_failure_recovery(manager, gateway_address)
        
        print("\n=== Demo completed ===")
        print("Press Ctrl+C to exit")
        
        # Keep running until interrupted
        while True:
            time.sleep(1)
            
    except Exception as e:
        print(f"Demo error: {e}")
    finally:
        manager.stop_all()


if __name__ == "__main__":
    main() 