# URL Shortener MVP

## Overview
A URL shortening service similar to bit.ly or tinyurl that converts long URLs into short, manageable links. This MVP demonstrates URL encoding/decoding, analytics tracking, custom domains, and high-performance link redirection.

## Technology Stack
- **Backend**: Go (Golang)
- **Database**: PostgreSQL for URL metadata, Redis for caching
- **Cache**: Redis for high-performance redirects
- **Analytics**: ClickHouse or PostgreSQL for click tracking
- **Base62 Encoding**: For generating short codes

## Key Features

### Core Functionality
- [ ] URL shortening with custom and auto-generated codes
- [ ] Fast URL redirection (< 100ms)
- [ ] Click analytics and tracking
- [ ] Custom domains support
- [ ] Expiration dates for URLs
- [ ] Bulk URL shortening
- [ ] QR code generation
- [ ] Link preview and metadata extraction

### API Endpoints
- `POST /shorten` - Create short URL
- `GET /{short_code}` - Redirect to original URL
- `GET /api/urls/{short_code}` - Get URL details
- `GET /api/urls/{short_code}/analytics` - Get click analytics
- `POST /api/urls/bulk` - Bulk shorten URLs
- `PUT /api/urls/{short_code}` - Update URL
- `DELETE /api/urls/{short_code}` - Delete URL

## Architecture Components

### 1. URL Service
- Handles URL shortening and retrieval
- Manages URL validation and metadata
- Implements collision detection

### 2. Redirect Service
- High-performance URL redirection
- Caching layer for fast lookups
- Analytics event triggering

### 3. Analytics Service
- Tracks click events
- Generates usage statistics
- Handles real-time and batch analytics

### 4. Code Generator
- Base62 encoding for short codes
- Collision detection and retry logic
- Custom code validation

## Database Schema

### URLs Table
```sql
- id (UUID)
- short_code (string, unique)
- original_url (text)
- title (string, nullable)
- description (text, nullable)
- favicon_url (string, nullable)
- creator_id (UUID, nullable)
- domain (string)
- clicks (bigint, default 0)
- is_active (boolean, default true)
- expires_at (timestamp, nullable)
- created_at (timestamp)
- updated_at (timestamp)
```

### Click Analytics Table
```sql
- id (UUID)
- short_code (string)
- ip_address (string)
- user_agent (string)
- referer (string, nullable)
- country (string, nullable)
- city (string, nullable)
- device_type (string, nullable)
- browser (string, nullable)
- os (string, nullable)
- clicked_at (timestamp)
```

### Users Table
```sql
- id (UUID)
- email (string, unique)
- password_hash (string)
- api_key (string, unique)
- tier (enum: free, premium, enterprise)
- urls_created (int, default 0)
- monthly_limit (int)
- custom_domain (string, nullable)
- created_at (timestamp)
```

### Domains Table
```sql
- id (UUID)
- domain_name (string, unique)
- user_id (UUID)
- is_verified (boolean, default false)
- ssl_enabled (boolean, default false)
- created_at (timestamp)
- verified_at (timestamp, nullable)
```

## URL Shortening Algorithm

### Base62 Encoding
```go
const base62Chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

func EncodeBase62(num uint64) string {
    if num == 0 {
        return "0"
    }
    
    var result []byte
    for num > 0 {
        result = append([]byte{base62Chars[num%62]}, result...)
        num /= 62
    }
    
    return string(result)
}

func DecodeBase62(str string) uint64 {
    var result uint64
    for _, char := range str {
        result = result*62 + uint64(strings.IndexByte(base62Chars, byte(char)))
    }
    return result
}
```

### Short Code Generation Strategies

#### 1. Counter-based
- Use auto-incrementing database counter
- Encode counter value to Base62
- Predictable but efficient

#### 2. Hash-based
- Hash original URL + timestamp
- Take first N characters of hash
- May have collisions

#### 3. Random Generation
- Generate random Base62 string
- Check for collisions
- Retry if collision detected

## Caching Strategy

### Redis Caching
```go
type URLCache struct {
    RedisClient *redis.Client
    TTL         time.Duration
}

func (c *URLCache) Get(shortCode string) (string, error) {
    return c.RedisClient.Get("url:" + shortCode).Result()
}

func (c *URLCache) Set(shortCode, originalURL string) error {
    return c.RedisClient.Set("url:" + shortCode, originalURL, c.TTL).Err()
}
```

### Cache Patterns
- **Write-through**: Update cache when URL is created/updated
- **Cache-aside**: Check cache first, fallback to database
- **TTL Strategy**: Expire popular URLs slowly, others quickly

## Analytics Implementation

### Real-time Analytics
```go
type ClickEvent struct {
    ShortCode    string    `json:"short_code"`
    IPAddress    string    `json:"ip_address"`
    UserAgent    string    `json:"user_agent"`
    Referer      string    `json:"referer"`
    Timestamp    time.Time `json:"timestamp"`
    GeoLocation  GeoData   `json:"geo_location"`
}

func (a *AnalyticsService) TrackClick(event ClickEvent) error {
    // Async processing
    go func() {
        // Parse user agent
        event.DeviceInfo = a.parseUserAgent(event.UserAgent)
        
        // Get geo location
        event.GeoLocation = a.getGeoLocation(event.IPAddress)
        
        // Store in database
        a.store(event)
        
        // Update counters
        a.updateCounters(event.ShortCode)
    }()
    
    return nil
}
```

### Aggregated Analytics
```sql
-- Daily clicks summary
SELECT 
    short_code,
    DATE(clicked_at) as date,
    COUNT(*) as clicks,
    COUNT(DISTINCT ip_address) as unique_visitors
FROM click_analytics 
WHERE short_code = $1 
GROUP BY short_code, DATE(clicked_at)
ORDER BY date DESC;

-- Top referrers
SELECT 
    referer,
    COUNT(*) as clicks
FROM click_analytics 
WHERE short_code = $1 AND referer IS NOT NULL
GROUP BY referer 
ORDER BY clicks DESC 
LIMIT 10;
```

## URL Metadata Extraction

### Link Preview
```go
func (s *URLService) ExtractMetadata(url string) (*URLMetadata, error) {
    resp, err := http.Get(url)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    
    doc, err := goquery.NewDocumentFromReader(resp.Body)
    if err != nil {
        return nil, err
    }
    
    metadata := &URLMetadata{
        Title:       doc.Find("title").First().Text(),
        Description: doc.Find("meta[name='description']").AttrOr("content", ""),
        Image:       doc.Find("meta[property='og:image']").AttrOr("content", ""),
        Favicon:     s.extractFavicon(doc, url),
    }
    
    return metadata, nil
}
```

## QR Code Generation

### QR Code Service
```go
import "github.com/skip2/go-qrcode"

func (q *QRService) GenerateQR(shortURL string, size int) ([]byte, error) {
    qr, err := qrcode.Encode(shortURL, qrcode.Medium, size)
    if err != nil {
        return nil, err
    }
    return qr, nil
}
```

## Performance Optimizations

### Database Optimizations
- Index on `short_code` for fast lookups
- Partition analytics table by date
- Use read replicas for analytics queries

### Redis Optimizations
- Connection pooling
- Cluster setup for high availability
- Appropriate TTL settings

### CDN Integration
- Cache redirects at edge locations
- Serve static assets (QR codes) from CDN
- Geographic distribution

## Rate Limiting

### Per-User Limits
```yaml
rate_limits:
  free_tier:
    urls_per_day: 100
    clicks_per_day: 1000
  premium_tier:
    urls_per_day: 10000
    clicks_per_day: 100000
  api_requests:
    per_minute: 60
    burst: 100
```

## Security Features

### URL Validation
```go
func (v *URLValidator) IsValidURL(url string) error {
    parsed, err := url.Parse(url)
    if err != nil {
        return err
    }
    
    // Check scheme
    if parsed.Scheme != "http" && parsed.Scheme != "https" {
        return errors.New("invalid scheme")
    }
    
    // Check for malicious domains
    if v.isMaliciousDomain(parsed.Host) {
        return errors.New("malicious domain detected")
    }
    
    return nil
}
```

### Spam Protection
- CAPTCHA for anonymous users
- Rate limiting per IP
- Blacklist of known malicious domains
- URL content scanning

## Custom Domains

### Domain Verification
```go
func (d *DomainService) VerifyDomain(domain string) error {
    // Check DNS TXT record
    txtRecords, err := net.LookupTXT(domain)
    if err != nil {
        return err
    }
    
    expectedRecord := fmt.Sprintf("short-link-verification=%s", d.generateVerificationCode())
    
    for _, record := range txtRecords {
        if record == expectedRecord {
            return d.markDomainVerified(domain)
        }
    }
    
    return errors.New("verification record not found")
}
```

## API Examples

### Shorten URL
```bash
curl -X POST "http://localhost:8080/shorten" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/very/long/url/path",
    "custom_code": "example",
    "expires_at": "2024-12-31T23:59:59Z"
  }'
```

### Get Analytics
```bash
curl "http://localhost:8080/api/urls/abc123/analytics?period=7d"
```

### Bulk Shorten
```bash
curl -X POST "http://localhost:8080/api/urls/bulk" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      {"url": "https://example1.com"},
      {"url": "https://example2.com"},
      {"url": "https://example3.com"}
    ]
  }'
```

## Monitoring and Alerts

### Key Metrics
- Redirect response time (< 100ms target)
- Cache hit ratio (> 95% target)
- Database connection pool usage
- Error rates by endpoint

### Health Checks
```go
func (h *HealthHandler) Check(w http.ResponseWriter, r *http.Request) {
    checks := map[string]bool{
        "database": h.checkDatabase(),
        "redis":    h.checkRedis(),
        "storage":  h.checkStorage(),
    }
    
    allHealthy := true
    for _, healthy := range checks {
        if !healthy {
            allHealthy = false
            break
        }
    }
    
    status := "healthy"
    if !allHealthy {
        status = "unhealthy"
        w.WriteHeader(http.StatusServiceUnavailable)
    }
    
    json.NewEncoder(w).Encode(map[string]interface{}{
        "status": status,
        "checks": checks,
        "timestamp": time.Now(),
    })
}
```

## Getting Started

1. Clone the repository
2. Install Go dependencies: `go mod tidy`
3. Set up PostgreSQL and Redis
4. Run database migrations
5. Configure domains and rate limits
6. Start the server: `go run main.go`

## Configuration
```yaml
# config.yaml
database:
  host: localhost
  port: 5432
  dbname: url_shortener

redis:
  host: localhost
  port: 6379
  
server:
  port: 8080
  default_domain: "short.ly"
  
url_shortener:
  code_length: 6
  default_ttl: "24h"
  enable_analytics: true
  
rate_limits:
  free_tier:
    daily_urls: 100
  premium_tier:
    daily_urls: 10000
```

## Future Enhancements
- A/B testing for different short codes
- Advanced analytics dashboard
- API rate limiting based on user tiers
- Integration with social media platforms
- Webhook support for click events
- Advanced fraud detection
- Mobile app with deep linking
- Enterprise features (SSO, custom branding) 