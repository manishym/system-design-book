# UUID Generator MVP

## Overview
A high-performance UUID generation service that supports multiple UUID versions and formats, providing globally unique identifiers for distributed systems. This MVP demonstrates various UUID algorithms, performance optimization, and collision detection.

## Technology Stack
- **Backend**: Go (Golang)
- **Database**: PostgreSQL for analytics and collision tracking
- **Cache**: Redis for performance metrics
- **Algorithms**: UUID v1, v4, v6, v7, and custom formats

## Key Features

### Core Functionality
- [ ] Multiple UUID versions (v1, v4, v6, v7)
- [ ] Custom UUID formats (Base62, Base36, Custom alphabet)
- [ ] Bulk UUID generation
- [ ] Collision detection and prevention
- [ ] Performance benchmarking
- [ ] Distributed generation coordination
- [ ] UUID validation and parsing
- [ ] Analytics and usage tracking

### API Endpoints
- `GET /uuid` - Generate single UUID (default v4)
- `GET /uuid/v1` - Generate UUID v1 (timestamp + MAC)
- `GET /uuid/v4` - Generate UUID v4 (random)
- `GET /uuid/v6` - Generate UUID v6 (timestamp ordered)
- `GET /uuid/v7` - Generate UUID v7 (timestamp + random)
- `POST /uuid/bulk` - Generate multiple UUIDs
- `GET /uuid/custom` - Generate custom format UUID
- `POST /uuid/validate` - Validate UUID format

## UUID Versions Explained

### UUID v1 (Timestamp + MAC Address)
- Based on current timestamp and MAC address
- Guarantees uniqueness within a network
- Can leak information about when/where generated
- Sortable by creation time

### UUID v4 (Random)
- Completely random (pseudo-random)
- Most commonly used version
- No information leakage
- Collision probability extremely low

### UUID v6 (Reordered Timestamp)
- Timestamp in sortable order
- Improvement over v1 for database performance
- Maintains temporal ordering

### UUID v7 (Timestamp + Random)
- Unix timestamp + random data
- Sortable and database-friendly
- Good balance of uniqueness and performance

## Architecture Components

### 1. UUID Generator Service
- Implements multiple UUID algorithms
- Handles format conversion
- Manages generation parameters

### 2. Node Coordinator
- Manages distributed node coordination
- Prevents clock conflicts
- Handles MAC address assignment

### 3. Collision Detector
- Tracks generated UUIDs (optional)
- Detects and reports collisions
- Maintains statistics

### 4. Performance Monitor
- Tracks generation performance
- Monitors throughput and latency
- Generates performance reports

## Implementation Details

### UUID v1 Implementation
```go
type UUIDv1Generator struct {
    NodeID    [6]byte
    ClockSeq  uint16
    LastTime  uint64
    mutex     sync.Mutex
}

func (g *UUIDv1Generator) Generate() string {
    g.mutex.Lock()
    defer g.mutex.Unlock()
    
    // Get current timestamp (100-nanosecond intervals since UUID epoch)
    now := time.Now()
    timestamp := uint64(now.Unix())*10000000 + uint64(now.Nanosecond()/100) + 0x01B21DD213814000
    
    // Handle clock sequence
    if timestamp <= g.LastTime {
        g.ClockSeq++
    } else {
        g.ClockSeq = uint16(rand.Intn(16384))
    }
    g.LastTime = timestamp
    
    // Construct UUID
    uuid := make([]byte, 16)
    
    // Time low (32 bits)
    binary.BigEndian.PutUint32(uuid[0:4], uint32(timestamp))
    
    // Time mid (16 bits)
    binary.BigEndian.PutUint16(uuid[4:6], uint16(timestamp>>32))
    
    // Time high and version (16 bits)
    binary.BigEndian.PutUint16(uuid[6:8], uint16(timestamp>>48)|0x1000)
    
    // Clock sequence and node
    binary.BigEndian.PutUint16(uuid[8:10], g.ClockSeq|0x8000)
    copy(uuid[10:16], g.NodeID[:])
    
    return formatUUID(uuid)
}
```

### UUID v4 Implementation
```go
func GenerateUUIDv4() string {
    uuid := make([]byte, 16)
    
    // Fill with random bytes
    _, err := rand.Read(uuid)
    if err != nil {
        panic(err)
    }
    
    // Set version (4) and variant bits
    uuid[6] = (uuid[6] & 0x0f) | 0x40  // Version 4
    uuid[8] = (uuid[8] & 0x3f) | 0x80  // Variant 10
    
    return formatUUID(uuid)
}
```

### UUID v7 Implementation
```go
func GenerateUUIDv7() string {
    uuid := make([]byte, 16)
    
    // Unix timestamp in milliseconds (48 bits)
    timestamp := time.Now().UnixMilli()
    binary.BigEndian.PutUint64(uuid[0:8], uint64(timestamp)<<16)
    
    // Random data (74 bits)
    rand.Read(uuid[6:16])
    
    // Set version (7) and variant bits
    uuid[6] = (uuid[6] & 0x0f) | 0x70  // Version 7
    uuid[8] = (uuid[8] & 0x3f) | 0x80  // Variant 10
    
    return formatUUID(uuid)
}
```

## Custom UUID Formats

### Base62 UUID
```go
const base62Chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

func GenerateBase62UUID(length int) string {
    uuid := make([]byte, length)
    for i := range uuid {
        uuid[i] = base62Chars[rand.Intn(len(base62Chars))]
    }
    return string(uuid)
}
```

### Snowflake-style ID
```go
type SnowflakeGenerator struct {
    NodeID      int64
    Sequence    int64
    LastTime    int64
    mutex       sync.Mutex
}

func (s *SnowflakeGenerator) Generate() int64 {
    s.mutex.Lock()
    defer s.mutex.Unlock()
    
    now := time.Now().UnixMilli()
    
    if now == s.LastTime {
        s.Sequence = (s.Sequence + 1) & 0xFFF  // 12 bits
        if s.Sequence == 0 {
            // Wait for next millisecond
            for now <= s.LastTime {
                now = time.Now().UnixMilli()
            }
        }
    } else {
        s.Sequence = 0
    }
    
    s.LastTime = now
    
    // Construct ID: timestamp(41) | nodeId(10) | sequence(12)
    id := (now << 22) | (s.NodeID << 12) | s.Sequence
    
    return id
}
```

## Database Schema

### UUID Generation Log Table
```sql
- id (bigserial)
- uuid_value (string)
- uuid_version (string)
- format_type (string)
- node_id (string)
- generated_at (timestamp)
- generation_time_us (int) -- microseconds
- client_ip (string, nullable)
- user_agent (string, nullable)
```

### Performance Metrics Table
```sql
- id (UUID)
- metric_type (enum: throughput, latency, collision)
- value (float)
- unit (string)
- node_id (string)
- measured_at (timestamp)
- additional_data (json)
```

### Node Registry Table
```sql
- node_id (string, primary key)
- mac_address (string)
- ip_address (string)
- status (enum: active, inactive, maintenance)
- last_heartbeat (timestamp)
- uuids_generated (bigint)
- created_at (timestamp)
```

## Performance Optimizations

### Batch Generation
```go
func (g *UUIDGenerator) GenerateBatch(count int, version string) ([]string, error) {
    uuids := make([]string, count)
    
    switch version {
    case "v4":
        // Pre-allocate random bytes
        randomBytes := make([]byte, count*16)
        rand.Read(randomBytes)
        
        for i := 0; i < count; i++ {
            uuid := randomBytes[i*16 : (i+1)*16]
            uuid[6] = (uuid[6] & 0x0f) | 0x40
            uuid[8] = (uuid[8] & 0x3f) | 0x80
            uuids[i] = formatUUID(uuid)
        }
    }
    
    return uuids, nil
}
```

### Memory Pool
```go
var uuidPool = sync.Pool{
    New: func() interface{} {
        return make([]byte, 16)
    },
}

func GenerateUUIDv4Pooled() string {
    uuid := uuidPool.Get().([]byte)
    defer uuidPool.Put(uuid)
    
    rand.Read(uuid)
    uuid[6] = (uuid[6] & 0x0f) | 0x40
    uuid[8] = (uuid[8] & 0x3f) | 0x80
    
    return formatUUID(uuid)
}
```

## Collision Detection

### Simple Collision Tracking
```go
type CollisionDetector struct {
    seen    map[string]bool
    mutex   sync.RWMutex
    maxSize int
}

func (cd *CollisionDetector) CheckCollision(uuid string) bool {
    cd.mutex.Lock()
    defer cd.mutex.Unlock()
    
    if cd.seen[uuid] {
        // Collision detected!
        return true
    }
    
    if len(cd.seen) >= cd.maxSize {
        // Clear half of the cache
        cd.clearHalf()
    }
    
    cd.seen[uuid] = true
    return false
}
```

### Probabilistic Collision Detection (Bloom Filter)
```go
import "github.com/bits-and-blooms/bloom/v3"

type BloomCollisionDetector struct {
    filter *bloom.BloomFilter
}

func NewBloomCollisionDetector(expectedElements uint, falsePositiveRate float64) *BloomCollisionDetector {
    return &BloomCollisionDetector{
        filter: bloom.NewWithEstimates(expectedElements, falsePositiveRate),
    }
}

func (bcd *BloomCollisionDetector) CheckCollision(uuid string) bool {
    if bcd.filter.TestString(uuid) {
        // Possible collision (may be false positive)
        return true
    }
    
    bcd.filter.AddString(uuid)
    return false
}
```

## Benchmarking and Testing

### Performance Benchmarks
```go
func BenchmarkUUIDv4Generation(b *testing.B) {
    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        GenerateUUIDv4()
    }
}

func BenchmarkUUIDv1Generation(b *testing.B) {
    generator := NewUUIDv1Generator()
    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        generator.Generate()
    }
}

func BenchmarkBulkGeneration(b *testing.B) {
    generator := NewUUIDGenerator()
    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        generator.GenerateBatch(1000, "v4")
    }
}
```

### Collision Testing
```go
func TestUUIDUniqueness(t *testing.T) {
    const iterations = 1000000
    seen := make(map[string]bool, iterations)
    
    for i := 0; i < iterations; i++ {
        uuid := GenerateUUIDv4()
        
        if seen[uuid] {
            t.Fatalf("Collision detected at iteration %d: %s", i, uuid)
        }
        
        seen[uuid] = true
    }
    
    t.Logf("Generated %d unique UUIDs without collision", iterations)
}
```

## Configuration

### Generator Configuration
```yaml
# config.yaml
uuid_generator:
  default_version: "v4"
  enable_collision_detection: false
  max_collision_cache_size: 1000000
  
node:
  id: "node-001"
  mac_address: "auto" # or specific MAC
  
performance:
  enable_metrics: true
  metrics_interval: "30s"
  batch_size_limit: 10000
  
api:
  rate_limit:
    requests_per_second: 1000
    burst_size: 100
```

## API Usage Examples

### Generate Single UUID
```bash
# Default (v4)
curl "http://localhost:8080/uuid"

# Specific version
curl "http://localhost:8080/uuid/v7"

# Custom format
curl "http://localhost:8080/uuid/custom?format=base62&length=12"
```

### Bulk Generation
```bash
curl -X POST "http://localhost:8080/uuid/bulk" \
  -H "Content-Type: application/json" \
  -d '{
    "count": 1000,
    "version": "v4",
    "format": "standard"
  }'
```

### Validate UUID
```bash
curl -X POST "http://localhost:8080/uuid/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "uuid": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

## Monitoring and Metrics

### Key Performance Indicators
- Generation throughput (UUIDs/second)
- Average generation latency
- Memory usage
- Collision rate (if detection enabled)
- API response times

### Health Checks
```go
func (h *HealthHandler) Check(w http.ResponseWriter, r *http.Request) {
    health := map[string]interface{}{
        "status": "healthy",
        "timestamp": time.Now(),
        "metrics": map[string]interface{}{
            "total_generated": atomic.LoadInt64(&h.totalGenerated),
            "average_latency_us": h.getAverageLatency(),
            "memory_usage_mb": h.getMemoryUsage(),
            "uptime_seconds": time.Since(h.startTime).Seconds(),
        },
    }
    
    json.NewEncoder(w).Encode(health)
}
```

## Getting Started

1. Clone the repository
2. Install Go dependencies: `go mod tidy`
3. Set up PostgreSQL (optional, for analytics)
4. Set up Redis (optional, for metrics)
5. Configure node settings
6. Start the server: `go run main.go`
7. Run benchmarks: `go test -bench=.`

## Load Testing

### Generate Load
```bash
# Using Apache Bench
ab -n 100000 -c 100 http://localhost:8080/uuid

# Using hey
hey -n 100000 -c 100 http://localhost:8080/uuid

# Custom load test
go run loadtest/main.go -duration=60s -workers=100 -endpoint="/uuid/v4"
```

## Future Enhancements
- UUID encryption for sensitive environments
- Distributed node coordination via etcd/Consul
- Custom UUID formats with validation rules
- UUID analytics and usage patterns
- Integration with service discovery
- UUID namespacing for multi-tenant environments
- Advanced collision prevention algorithms
- UUID compression for storage optimization 