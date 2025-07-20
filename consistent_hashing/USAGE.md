# Consistent Hashing System Usage Guide

This system implements a distributed consistent hashing solution with two main services:

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  KV Store A │     │  KV Store B │     │  KV Store C │
│  Port: 8080 │     │  Port: 8081 │     │  Port: 8082 │
└─────┬───────┘     └─────┬───────┘     └─────┬───────┘
      │                   │                   │
      └─────────────────┬─┴─┬─────────────────┘
                        │   │ Heartbeats
                        ▼   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Gateway X  │◄────┤  Gateway Y  │────►│  Gateway Z  │
│  Port: 8000 │     │  Port: 8001 │     │  Port: 8002 │
│  Raft: 8001 │     │  Raft: 8002 │     │  Raft: 8003 │
└─────────────┘     └─────────────┘     └─────────────┘
        ▲                   ▲                   ▲
        └───────────────────┼───────────────────┘
                      Gossip Protocol
```

## Components

### 1. Gateway Service (`gateway_service.py`)
- **Purpose**: Manages the consistent hash ring
- **Features**:
  - Receives heartbeats from KV stores
  - Uses Raft consensus for ring updates
  - Gossips heartbeat information to other gateways
  - Automatically removes dead nodes from the ring
  - Provides REST API for key-to-node mapping

### 2. KV Store Service (`kvstore_service.py`)
- **Purpose**: Stores key-value pairs and maintains liveness
- **Features**:
  - In-memory key-value storage
  - Automatic registration with gateway
  - Periodic heartbeat transmission
  - REST API for CRUD operations

### 3. Client (`KVStoreClient` class)
- **Purpose**: Provides easy interface for applications
- **Features**:
  - Automatic node discovery via gateway
  - Transparent consistent hashing
  - PUT/GET/DELETE operations

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage Examples

### Starting the System

#### 1. Start Gateway Services (3 instances for fault tolerance)

```bash
# Terminal 1 - Gateway 1
python gateway_service.py --gateway-id gateway-1 --port 8000 --raft-port 8001 --peers localhost:8001 localhost:8002

# Terminal 2 - Gateway 2  
python gateway_service.py --gateway-id gateway-2 --port 8001 --raft-port 8002 --peers localhost:8000 localhost:8002

# Terminal 3 - Gateway 3
python gateway_service.py --gateway-id gateway-3 --port 8002 --raft-port 8003 --peers localhost:8000 localhost:8001
```

#### 2. Start KV Store Services

```bash
# Terminal 4 - KV Store A
python kvstore_service.py --node-id kvstore-A --port 8080 --gateway localhost:8000

# Terminal 5 - KV Store B
python kvstore_service.py --node-id kvstore-B --port 8081 --gateway localhost:8000

# Terminal 6 - KV Store C  
python kvstore_service.py --node-id kvstore-C --port 8082 --gateway localhost:8000
```

### Using the Client

```python
from kvstore_service import KVStoreClient

# Create client
client = KVStoreClient("localhost:8000")

# Store data
client.put("user:1001", {"name": "Alice", "age": 25})
client.put("product:2001", {"name": "Laptop", "price": 999.99})

# Retrieve data
user = client.get("user:1001")
print(user)  # {"name": "Alice", "age": 25}

# Delete data
client.delete("user:1001")
```

### Direct API Usage

#### Gateway API

```bash
# Get ring status
curl http://localhost:8000/ring/status

# Find node responsible for a key
curl http://localhost:8000/nodes/user:1001

# List all nodes
curl http://localhost:8000/nodes
```

#### KV Store API

```bash
# Store a key-value pair
curl -X POST http://localhost:8080/put \
  -H "Content-Type: application/json" \
  -d '{"key": "user:1001", "value": {"name": "Alice"}}'

# Retrieve a value
curl http://localhost:8080/get/user:1001

# Delete a key
curl -X DELETE http://localhost:8080/delete/user:1001

# List all keys in this store
curl http://localhost:8080/keys

# Check health
curl http://localhost:8080/health
```

## Running the Demo

The system includes a comprehensive demo that shows all features:

```bash
python example_demo.py
```

The demo will:
1. Start 3 gateway services
2. Start 3 KV store services
3. Demonstrate basic operations (PUT/GET/DELETE)
4. Show consistent hashing key distribution
5. Simulate node failure and recovery

## Key Features Demonstrated

### 1. Consistent Hashing
- Keys are automatically distributed across available nodes
- Adding/removing nodes causes minimal data redistribution
- Each key consistently maps to the same node

### 2. High Availability
- Multiple gateway instances provide redundancy
- Raft consensus ensures consistent view of the ring
- Automatic failure detection and recovery

### 3. Gossip Protocol
- Heartbeat information spreads quickly across gateways
- Provides better failure detection than individual monitoring
- Reduces network overhead compared to full mesh monitoring

### 4. Fault Tolerance
- Dead nodes are automatically removed from the ring
- Keys previously mapped to dead nodes are redistributed
- System continues operating with remaining nodes

## Configuration

### Gateway Service Parameters
- `--gateway-id`: Unique identifier for this gateway
- `--port`: HTTP API port
- `--raft-port`: Raft consensus port  
- `--peers`: List of other gateway addresses

### KV Store Parameters
- `--node-id`: Unique identifier for this KV store
- `--port`: HTTP API port
- `--gateway`: Gateway address to register with

### Tunable Settings

In `gateway_service.py`:
```python
self.heartbeat_timeout = 30     # seconds until node considered dead
self.gossip_interval = 5        # gossip message frequency
self.health_check_interval = 10 # health check frequency
```

In `kvstore_service.py`:
```python
self.heartbeat_interval = 10           # heartbeat frequency
self.registration_retry_interval = 5   # retry registration frequency
```

## Monitoring and Debugging

### Gateway Logs
```bash
# Watch gateway logs
tail -f gateway_service.log
```

### Ring Status
```bash
# Check which nodes are in the ring
curl http://localhost:8000/ring/status | jq .

# See key distribution
for key in user:1001 product:2001 order:3001; do
  echo "$key -> $(curl -s http://localhost:8000/nodes/$key | jq -r .node.node_id)"
done
```

### Node Health
```bash
# Check individual node health
curl http://localhost:8080/health
curl http://localhost:8081/health  
curl http://localhost:8082/health
```

## Troubleshooting

### Common Issues

1. **Gateway won't start**: 
   - Check ports aren't already in use
   - Ensure peer addresses are correct

2. **KV store won't register**:
   - Verify gateway is running and accessible
   - Check network connectivity

3. **Keys not found after node failure**:
   - Wait for failure detection (30+ seconds)
   - Check ring status to confirm node removal

4. **Raft consensus issues**:
   - Ensure at least 2 out of 3 gateways are running
   - Check Raft log files for errors

### Performance Tuning

- **Heartbeat frequency**: Balance between failure detection speed and network overhead
- **Virtual nodes**: Increase for better load distribution (modify hash_ring configuration)
- **Raft timeouts**: Adjust for network latency characteristics

## Production Considerations

1. **Persistence**: Current implementation uses in-memory storage
2. **Security**: Add authentication and encryption for production
3. **Load balancing**: Consider load balancer in front of gateways
4. **Monitoring**: Add metrics collection and alerting
5. **Backup**: Implement data replication across multiple nodes

## API Reference

### Gateway Service

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/heartbeat` | POST | Receive heartbeat from KV store |
| `/nodes` | GET | List all nodes in ring |
| `/nodes/<key>` | GET | Get node responsible for key |
| `/ring/status` | GET | Get ring statistics |
| `/gossip` | POST | Receive gossip message |

### KV Store Service  

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/put` | POST | Store key-value pair |
| `/get/<key>` | GET | Retrieve value by key |
| `/delete/<key>` | DELETE | Delete key-value pair |
| `/keys` | GET | List all keys |
| `/health` | GET | Health check |
| `/stats` | GET | Node statistics | 