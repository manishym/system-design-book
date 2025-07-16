package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"time"

	"github.com/go-redis/redis/v8"
)

var ctx = context.Background()

var (
	// Configuration variables
	redisAddr      string
	redisPassword  string
	redisDB        int
	bucketCapacity int
	refillInterval time.Duration
	serverPort     string
)

var rdb *redis.Client

func init() {
	// Define command line flags with default values
	flag.StringVar(&redisAddr, "redis-addr", "redis-master:6379", "Redis server address")
	flag.StringVar(&redisPassword, "redis-password", "", "Redis password")
	flag.IntVar(&redisDB, "redis-db", 0, "Redis database number")
	flag.IntVar(&bucketCapacity, "bucket-capacity", 5, "Token bucket capacity")
	flag.DurationVar(&refillInterval, "refill-interval", 10*time.Second, "Token refill interval")
	flag.StringVar(&serverPort, "port", "8080", "Server port")
}

func main() {
	// Parse command line flags
	flag.Parse()

	// Log configuration
	log.Printf("Starting rate limiter with config:")
	log.Printf("  Redis Address: %s", redisAddr)
	log.Printf("  Redis DB: %d", redisDB)
	log.Printf("  Bucket Capacity: %d", bucketCapacity)
	log.Printf("  Refill Interval: %v", refillInterval)
	log.Printf("  Server Port: %s", serverPort)

	// Initialize Redis client
	rdb = redis.NewClient(&redis.Options{
		Addr:     redisAddr,
		Password: redisPassword,
		DB:       redisDB,
	})

	// Test Redis connection
	_, err := rdb.Ping(ctx).Result()
	if err != nil {
		log.Fatalf("Failed to connect to Redis: %v", err)
	}
	log.Println("Successfully connected to Redis")

	// Setup HTTP handlers
	http.HandleFunc("/check", rateLimitHandler)
	http.HandleFunc("/health", healthHandler)

	log.Printf("Rate limiter running on port %s", serverPort)
	log.Fatal(http.ListenAndServe(":"+serverPort, nil))
}

func rateLimitHandler(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	if userID == "" {
		http.Error(w, "user_id required", http.StatusBadRequest)
		return
	}

	keyTokens := fmt.Sprintf("ratelimit:%s:tokens", userID)
	keyTimestamp := fmt.Sprintf("ratelimit:%s:ts", userID)

	now := time.Now().Unix()

	// Get current state
	tokensStr, _ := rdb.Get(ctx, keyTokens).Result()
	tsStr, _ := rdb.Get(ctx, keyTimestamp).Result()

	var tokens int
	var lastRefill int64

	tokens, _ = strconv.Atoi(tokensStr)
	lastRefill, _ = strconv.ParseInt(tsStr, 10, 64)

	// refill tokens
	if tokensStr == "" || now-lastRefill >= int64(refillInterval.Seconds()) {
		tokens = bucketCapacity
		lastRefill = now
	}

	if tokens > 0 {
		tokens -= 1
		rdb.Set(ctx, keyTokens, tokens, refillInterval)
		rdb.Set(ctx, keyTimestamp, lastRefill, refillInterval)

		// Set response headers
		w.Header().Set("X-RateLimit-Limit", strconv.Itoa(bucketCapacity))
		w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(tokens))
		w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(lastRefill+int64(refillInterval.Seconds()), 10))

		w.WriteHeader(http.StatusOK)
		w.Write([]byte("allowed"))
	} else {
		// Set response headers for rate limit exceeded
		w.Header().Set("X-RateLimit-Limit", strconv.Itoa(bucketCapacity))
		w.Header().Set("X-RateLimit-Remaining", "0")
		w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(lastRefill+int64(refillInterval.Seconds()), 10))
		w.Header().Set("Retry-After", strconv.Itoa(int(refillInterval.Seconds())))

		w.WriteHeader(http.StatusTooManyRequests)
		w.Write([]byte("rate limit exceeded"))
	}
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	// Check Redis connection
	_, err := rdb.Ping(ctx).Result()
	if err != nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		w.Write([]byte("Redis connection failed"))
		return
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}
