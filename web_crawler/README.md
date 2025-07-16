# Web Crawler MVP

## Overview
A distributed web crawler system that can efficiently crawl and index web pages while respecting robots.txt, handling rate limiting, and avoiding duplicate content. This MVP demonstrates web scraping, content extraction, and distributed crawling architecture.

## Technology Stack
- **Backend**: Go (Golang)
- **Database**: PostgreSQL for metadata, Elasticsearch for search indexing
- **Queue**: Redis for URL queue management
- **Storage**: AWS S3/MinIO for storing crawled content
- **Parsing**: goquery for HTML parsing, colly for crawling framework

## Key Features

### Core Functionality
- [ ] Distributed web crawling
- [ ] Robots.txt compliance
- [ ] Rate limiting per domain
- [ ] Duplicate URL detection
- [ ] Content extraction and parsing
- [ ] Link discovery and following
- [ ] Sitemap parsing
- [ ] Content deduplication
- [ ] Crawl scheduling and prioritization

### API Endpoints
- `POST /crawl/start` - Start crawling a URL/domain
- `GET /crawl/status/{job_id}` - Get crawl job status
- `POST /crawl/stop/{job_id}` - Stop crawl job
- `GET /crawl/stats` - Get crawling statistics
- `GET /pages/{id}` - Get crawled page content
- `GET /search?q={query}` - Search crawled content
- `POST /crawl/schedule` - Schedule recurring crawls

## Architecture Components

### 1. Crawler Manager
- Manages crawl jobs and workers
- Distributes work across multiple nodes
- Handles job scheduling and prioritization

### 2. URL Queue
- Maintains queue of URLs to crawl
- Implements priority queuing
- Handles deduplication

### 3. Content Processor
- Extracts text, links, and metadata
- Handles content deduplication
- Generates content fingerprints

### 4. Storage Manager
- Stores raw HTML content
- Manages compressed storage
- Handles content versioning

## Database Schema

### Crawl Jobs Table
```sql
- id (UUID)
- name (string)
- start_urls (json)
- domain_whitelist (json, nullable)
- domain_blacklist (json, nullable)
- max_depth (int)
- max_pages (int, nullable)
- crawl_delay (int) -- milliseconds
- status (enum: pending, running, paused, completed, failed)
- pages_crawled (int)
- pages_found (int)
- started_at (timestamp, nullable)
- completed_at (timestamp, nullable)
- created_at (timestamp)
- updated_at (timestamp)
```

### URLs Table
```sql
- id (UUID)
- url (text, unique)
- url_hash (string, indexed)
- domain (string)
- discovered_at (timestamp)
- last_crawled (timestamp, nullable)
- status (enum: pending, crawled, failed, blocked)
- crawl_count (int, default 0)
- priority (int, default 0)
- depth (int)
- parent_url_id (UUID, nullable)
- job_id (UUID)
```

### Pages Table
```sql
- id (UUID)
- url_id (UUID)
- title (text)
- content (text)
- content_hash (string)
- html_content_path (string) -- S3 path
- status_code (int)
- content_type (string)
- content_length (bigint)
- headers (json)
- meta_description (text)
- meta_keywords (text)
- links_extracted (int)
- images_extracted (int)
- crawled_at (timestamp)
- processing_time_ms (int)
```

### Robots Table
```sql
- id (UUID)
- domain (string, unique)
- robots_txt (text)
- crawl_delay (int, nullable)
- last_fetched (timestamp)
- is_valid (boolean)
- user_agent_rules (json)
```

### Links Table
```sql
- id (UUID)
- source_page_id (UUID)
- target_url (text)
- anchor_text (text)
- link_type (enum: internal, external)
- discovered_at (timestamp)
```

## Crawler Implementation

### Basic Crawler Structure
```go
type WebCrawler struct {
    queue       URLQueue
    storage     ContentStorage
    robotsCache map[string]*RobotsRule
    rateLimiter map[string]*rate.Limiter
    client      *http.Client
    workers     int
    userAgent   string
}

func (c *WebCrawler) Start(ctx context.Context, job *CrawlJob) error {
    // Initialize worker pool
    for i := 0; i < c.workers; i++ {
        go c.worker(ctx, job)
    }
    
    // Add seed URLs to queue
    for _, url := range job.StartURLs {
        c.queue.Add(url, 0) // depth 0
    }
    
    return c.waitForCompletion(ctx)
}

func (c *WebCrawler) worker(ctx context.Context, job *CrawlJob) {
    for {
        select {
        case <-ctx.Done():
            return
        default:
            url, depth, ok := c.queue.Pop()
            if !ok {
                time.Sleep(100 * time.Millisecond)
                continue
            }
            
            if err := c.crawlURL(url, depth, job); err != nil {
                log.Printf("Error crawling %s: %v", url, err)
            }
        }
    }
}
```

### URL Crawling Process
```go
func (c *WebCrawler) crawlURL(url string, depth int, job *CrawlJob) error {
    // Check robots.txt
    if !c.isAllowedByRobots(url) {
        return fmt.Errorf("blocked by robots.txt")
    }
    
    // Rate limiting
    domain := extractDomain(url)
    if err := c.waitForRateLimit(domain); err != nil {
        return err
    }
    
    // Fetch page
    resp, err := c.client.Get(url)
    if err != nil {
        return err
    }
    defer resp.Body.Close()
    
    // Parse content
    page, err := c.parsePage(url, resp)
    if err != nil {
        return err
    }
    
    // Store content
    if err := c.storage.StorePage(page); err != nil {
        return err
    }
    
    // Extract and queue links
    if depth < job.MaxDepth {
        links := c.extractLinks(page.HTML, url)
        for _, link := range links {
            if c.shouldCrawlURL(link, job) {
                c.queue.Add(link, depth+1)
            }
        }
    }
    
    return nil
}
```

## Robots.txt Handling

### Robots Parser
```go
type RobotsRule struct {
    UserAgent    string
    Allow        []string
    Disallow     []string
    CrawlDelay   time.Duration
    Sitemap      []string
}

func (r *RobotsManager) FetchRobots(domain string) (*RobotsRule, error) {
    robotsURL := fmt.Sprintf("https://%s/robots.txt", domain)
    
    resp, err := http.Get(robotsURL)
    if err != nil {
        return &RobotsRule{}, nil // Allow crawling if robots.txt unavailable
    }
    defer resp.Body.Close()
    
    if resp.StatusCode != 200 {
        return &RobotsRule{}, nil
    }
    
    content, err := io.ReadAll(resp.Body)
    if err != nil {
        return nil, err
    }
    
    return r.parseRobots(string(content)), nil
}

func (r *RobotsManager) IsAllowed(url, userAgent string) bool {
    domain := extractDomain(url)
    rules, exists := r.cache[domain]
    if !exists {
        rules, _ = r.FetchRobots(domain)
        r.cache[domain] = rules
    }
    
    return r.checkRules(url, userAgent, rules)
}
```

## Content Processing

### HTML Parsing and Extraction
```go
import "github.com/PuerkitoBio/goquery"

type PageContent struct {
    URL             string
    Title           string
    Content         string
    MetaDescription string
    MetaKeywords    string
    Links           []Link
    Images          []Image
    Headers         map[string]string
    StatusCode      int
}

func (p *ContentProcessor) ParsePage(url string, resp *http.Response) (*PageContent, error) {
    body, err := io.ReadAll(resp.Body)
    if err != nil {
        return nil, err
    }
    
    doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(body)))
    if err != nil {
        return nil, err
    }
    
    page := &PageContent{
        URL:        url,
        StatusCode: resp.StatusCode,
        Headers:    make(map[string]string),
    }
    
    // Extract title
    page.Title = doc.Find("title").First().Text()
    
    // Extract meta tags
    page.MetaDescription = doc.Find("meta[name='description']").AttrOr("content", "")
    page.MetaKeywords = doc.Find("meta[name='keywords']").AttrOr("content", "")
    
    // Extract text content
    page.Content = p.extractTextContent(doc)
    
    // Extract links
    page.Links = p.extractLinks(doc, url)
    
    // Extract images
    page.Images = p.extractImages(doc, url)
    
    return page, nil
}

func (p *ContentProcessor) extractTextContent(doc *goquery.Document) string {
    // Remove script and style elements
    doc.Find("script, style").Remove()
    
    // Get text content
    text := doc.Find("body").Text()
    
    // Clean up whitespace
    text = strings.Join(strings.Fields(text), " ")
    
    return text
}
```

## URL Queue Management

### Priority Queue Implementation
```go
type URLQueue struct {
    redis  *redis.Client
    name   string
}

type QueueItem struct {
    URL      string    `json:"url"`
    Depth    int       `json:"depth"`
    Priority int       `json:"priority"`
    AddedAt  time.Time `json:"added_at"`
}

func (q *URLQueue) Add(url string, depth int) error {
    // Check for duplicates
    exists, err := q.redis.SIsMember("crawled_urls", url).Result()
    if err != nil {
        return err
    }
    if exists {
        return nil // Already crawled
    }
    
    item := QueueItem{
        URL:      url,
        Depth:    depth,
        Priority: q.calculatePriority(url, depth),
        AddedAt:  time.Now(),
    }
    
    data, err := json.Marshal(item)
    if err != nil {
        return err
    }
    
    // Add to priority queue
    return q.redis.ZAdd(q.name, &redis.Z{
        Score:  float64(item.Priority),
        Member: string(data),
    }).Err()
}

func (q *URLQueue) Pop() (string, int, bool) {
    result, err := q.redis.ZPopMax(q.name).Result()
    if err != nil || len(result) == 0 {
        return "", 0, false
    }
    
    var item QueueItem
    if err := json.Unmarshal([]byte(result[0].Member.(string)), &item); err != nil {
        return "", 0, false
    }
    
    return item.URL, item.Depth, true
}
```

## Rate Limiting

### Domain-based Rate Limiting
```go
import "golang.org/x/time/rate"

type RateLimiter struct {
    limiters map[string]*rate.Limiter
    mutex    sync.RWMutex
    default  rate.Limit
}

func NewRateLimiter(defaultRate rate.Limit) *RateLimiter {
    return &RateLimiter{
        limiters: make(map[string]*rate.Limiter),
        default:  defaultRate,
    }
}

func (rl *RateLimiter) Wait(ctx context.Context, domain string) error {
    rl.mutex.RLock()
    limiter, exists := rl.limiters[domain]
    rl.mutex.RUnlock()
    
    if !exists {
        rl.mutex.Lock()
        limiter, exists = rl.limiters[domain]
        if !exists {
            limiter = rate.NewLimiter(rl.default, 1)
            rl.limiters[domain] = limiter
        }
        rl.mutex.Unlock()
    }
    
    return limiter.Wait(ctx)
}

func (rl *RateLimiter) SetDomainRate(domain string, r rate.Limit) {
    rl.mutex.Lock()
    defer rl.mutex.Unlock()
    rl.limiters[domain] = rate.NewLimiter(r, 1)
}
```

## Content Deduplication

### Content Fingerprinting
```go
import "crypto/sha256"

func (cd *ContentDeduplicator) GenerateFingerprint(content string) string {
    // Normalize content
    normalized := cd.normalizeContent(content)
    
    // Generate hash
    hash := sha256.Sum256([]byte(normalized))
    return fmt.Sprintf("%x", hash)
}

func (cd *ContentDeduplicator) normalizeContent(content string) string {
    // Remove extra whitespace
    content = strings.Join(strings.Fields(content), " ")
    
    // Convert to lowercase
    content = strings.ToLower(content)
    
    // Remove common words (optional)
    words := strings.Fields(content)
    var filtered []string
    for _, word := range words {
        if !cd.isStopWord(word) {
            filtered = append(filtered, word)
        }
    }
    
    return strings.Join(filtered, " ")
}

func (cd *ContentDeduplicator) IsDuplicate(fingerprint string) (bool, error) {
    exists, err := cd.redis.SIsMember("content_fingerprints", fingerprint).Result()
    if err != nil {
        return false, err
    }
    
    if !exists {
        // Add to set
        cd.redis.SAdd("content_fingerprints", fingerprint)
    }
    
    return exists, nil
}
```

## Configuration

### Crawler Configuration
```yaml
# config.yaml
crawler:
  workers: 10
  user_agent: "WebCrawler/1.0 (+http://example.com/bot)"
  default_crawl_delay: 1000  # milliseconds
  max_depth: 5
  max_pages_per_domain: 10000
  
  request_timeout: 30s
  max_response_size: 10MB
  
rate_limiting:
  default_requests_per_second: 1
  burst_size: 5
  
storage:
  content_compression: gzip
  max_content_size: 1MB
  
duplicate_detection:
  enabled: true
  algorithm: "sha256"
  
politeness:
  respect_robots_txt: true
  robots_cache_ttl: 24h
  crawl_delay_multiplier: 1.5
```

## Monitoring and Analytics

### Crawl Metrics
```go
type CrawlMetrics struct {
    JobID              string
    URLsQueued         int64
    URLsCrawled        int64
    URLsFailed         int64
    PagesStored        int64
    DuplicatesSkipped  int64
    BytesDownloaded    int64
    AverageResponseTime time.Duration
    ErrorRate          float64
}

func (m *MetricsCollector) UpdateMetrics(jobID string, event string, data map[string]interface{}) {
    key := fmt.Sprintf("metrics:%s", jobID)
    
    switch event {
    case "url_crawled":
        m.redis.HIncrBy(key, "urls_crawled", 1)
    case "url_failed":
        m.redis.HIncrBy(key, "urls_failed", 1)
    case "page_stored":
        m.redis.HIncrBy(key, "pages_stored", 1)
        if size, ok := data["content_size"].(int64); ok {
            m.redis.HIncrBy(key, "bytes_downloaded", size)
        }
    }
}
```

## API Usage Examples

### Start Crawl Job
```bash
curl -X POST "http://localhost:8080/crawl/start" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Example.com Crawl",
    "start_urls": ["https://example.com"],
    "max_depth": 3,
    "max_pages": 1000,
    "crawl_delay": 1000,
    "domain_whitelist": ["example.com"]
  }'
```

### Get Crawl Status
```bash
curl "http://localhost:8080/crawl/status/job-123"
```

### Search Crawled Content
```bash
curl "http://localhost:8080/search?q=golang+tutorial&limit=10"
```

## Getting Started

1. Clone the repository
2. Install Go dependencies: `go mod tidy`
3. Set up PostgreSQL and Redis
4. Set up Elasticsearch (optional, for search)
5. Configure S3/MinIO for content storage
6. Run database migrations
7. Configure crawler settings
8. Start the crawler service: `go run main.go`

## Future Enhancements
- JavaScript rendering with headless browsers
- Image and document crawling
- API crawling and structured data extraction
- Machine learning for content classification
- Advanced duplicate detection (shingling, simhash)
- Distributed crawling coordination
- Real-time crawl monitoring dashboard
- Content change detection and notifications 