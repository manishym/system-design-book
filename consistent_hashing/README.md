# Consistent Hashing MVP

## Overview
A consistent hashing implementation that demonstrates efficient data distribution across nodes with minimal redistribution when nodes are added or removed. This MVP showcases the core algorithm and its applications in distributed systems.

## Technology Stack
- **Language**: Go (Golang)
- **Hashing**: SHA-256 for hash function
- **Data Structures**: Ring (circular array/map)
- **Visualization**: Optional web UI for ring visualization

## Key Features

### Core Functionality
- [ ] Consistent hashing ring implementation
- [ ] Virtual nodes for better load distribution
- [ ] Node addition and removal
- [ ] Key-to-node mapping
- [ ] Load balancing metrics
- [ ] Replication support
- [ ] Ring visualization
- [ ] Performance benchmarking

### API Endpoints
- `POST /nodes` - Add node to ring
- `DELETE /nodes/{id}` - Remove node from ring
- `GET /nodes` - List all nodes
- `GET /nodes/{key}` - Find node responsible for key
- `GET /ring/status` - Get ring statistics
- `GET /ring/visualize` - Get ring visualization data
- `POST /keys/distribute` - Distribute keys across ring

## Architecture Components

### 1. Hash Ring
- Maintains sorted list of nodes on ring
- Implements consistent hashing algorithm
- Handles virtual nodes for load balancing

### 2. Node Manager
- Manages node lifecycle (add/remove)
- Tracks node health and status
- Handles node metadata

### 3. Key Locator
- Maps keys to responsible nodes
- Implements clockwise search on ring
- Handles replication logic

### 4. Load Balancer
- Monitors key distribution
- Calculates load statistics
- Suggests rebalancing when needed

## Core Algorithm

### Ring Structure
```go
type HashRing struct {
    nodes        map[uint32]string  // hash -> node_id
    sortedHashes []uint32           // sorted hash values
    virtualNodes int                // virtual nodes per physical node
    replicas     int                // replication factor
}
```

### Key Mapping Process
1. Hash the key using SHA-256
2. Find first node clockwise from hash position
3. Return node responsible for the key
4. Handle replication if required

## Implementation Details

### Virtual Nodes
- Each physical node gets multiple positions on ring
- Better load distribution across nodes
- Configurable virtual node count (default: 150)

### Node Addition
1. Generate virtual node positions
2. Insert into sorted ring
3. Redistribute only affected keys
4. Update replication mappings

### Node Removal
1. Remove all virtual nodes from ring
2. Redistribute keys to next nodes
3. Update replication mappings
4. Handle data migration

## Performance Characteristics

### Time Complexity
- Key lookup: O(log N) where N is number of virtual nodes
- Node addition: O(V log N) where V is virtual nodes per physical node
- Node removal: O(V log N)

### Space Complexity
- O(N * V) where N is physical nodes and V is virtual nodes per node

## Configuration

### Ring Parameters
```yaml
virtual_nodes_per_node: 150
replication_factor: 3
hash_function: "sha256"
ring_size: 2^32
load_balance_threshold: 0.25
```

## Data Structures

### Node Information
```go
type Node struct {
    ID       string
    Address  string
    Weight   float64
    Status   string // active, inactive, draining
    Load     int64  // current key count
    AddedAt  time.Time
}
```

### Key Distribution Stats
```go
type RingStats struct {
    TotalNodes      int
    TotalKeys       int64
    AverageLoad     float64
    LoadStdDev      float64
    MaxLoad         int64
    MinLoad         int64
    LoadImbalance   float64
}
```

## Example Usage

### Basic Ring Operations
```go
// Create new ring
ring := NewHashRing(150, 3) // 150 virtual nodes, 3 replicas

// Add nodes
ring.AddNode("node1", "192.168.1.1:8080")
ring.AddNode("node2", "192.168.1.2:8080") 
ring.AddNode("node3", "192.168.1.3:8080")

// Find node for key
node := ring.GetNode("user:12345")
replicas := ring.GetReplicas("user:12345")

// Remove node
ring.RemoveNode("node2")
```

## API Examples

### Add Node
```bash
curl -X POST "http://localhost:8080/nodes" \
  -H "Content-Type: application/json" \
  -d '{"id": "node1", "address": "192.168.1.1:8080", "weight": 1.0}'
```

### Find Node for Key
```bash
curl "http://localhost:8080/nodes/user:12345"
```

### Get Ring Statistics
```bash
curl "http://localhost:8080/ring/status"
```

## Load Balancing Metrics

### Standard Deviation Calculation
```go
func (r *HashRing) CalculateLoadImbalance() float64 {
    loads := r.GetNodeLoads()
    avg := r.GetAverageLoad()
    
    variance := 0.0
    for _, load := range loads {
        variance += math.Pow(float64(load) - avg, 2)
    }
    
    stdDev := math.Sqrt(variance / float64(len(loads)))
    return stdDev / avg // coefficient of variation
}
```

## Testing and Benchmarks

### Load Distribution Test
- Add varying number of nodes
- Distribute 1M keys randomly
- Measure load distribution statistics
- Verify minimal redistribution on node changes

### Performance Benchmarks
- Key lookup performance
- Node addition/removal performance
- Memory usage with different virtual node counts

## Getting Started

1. Clone the repository
2. Install Go dependencies: `go mod tidy`
3. Run the example: `go run examples/basic_ring.go`
4. Start the HTTP server: `go run main.go`
5. Run benchmarks: `go test -bench=.`

## Visualization

The system includes a web-based visualization showing:
- Ring structure with nodes and virtual nodes
- Key distribution across nodes
- Load balancing metrics
- Real-time updates when nodes are added/removed

## Future Enhancements
- Support for different hash functions
- Weighted consistent hashing
- Integration with real distributed storage systems
- Advanced rebalancing strategies
- Failure detection and automatic node replacement
- Geographic aware node placement 