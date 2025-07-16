package main

import (
	"context"
	"flag"
	"fmt"
	"io/ioutil"
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
	refillRate     float64 // tokens per second instead of interval
	serverPort     string
)

var rdb *redis.Client
var tokenBucketScript *redis.Script

func init() {
	// Define command line flags with default values
	flag.StringVar(&redisAddr, "redis-addr", "redis-master:6379", "Redis server address")
	flag.StringVar(&redisPassword, "redis-password", "", "Redis password")
	flag.IntVar(&redisDB, "redis-db", 0, "Redis database number")
	flag.IntVar(&bucketCapacity, "bucket-capacity", 5, "Token bucket capacity")
	flag.Float64Var(&refillRate, "refill-rate", 0.1, "Token refill rate (tokens per second)")
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
	log.Printf("  Refill Rate: %.2f tokens/second", refillRate)
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

	// Load the token bucket Lua script
	err = loadTokenBucketScript()
	if err != nil {
		log.Fatalf("Failed to load token bucket script: %v", err)
	}
	log.Println("Successfully loaded token bucket Lua script")

	// Setup HTTP handlers
	http.HandleFunc("/check", rateLimitHandler)
	http.HandleFunc("/health", healthHandler)

	log.Printf("Rate limiter running on port %s", serverPort)
	log.Fatal(http.ListenAndServe(":"+serverPort, nil))
}

func loadTokenBucketScript() error {
	// Read the Lua script from file
	scriptContent, err := ioutil.ReadFile("token_bucket.lua")
	if err != nil {
		return fmt.Errorf("failed to read token_bucket.lua: %w", err)
	}

	// Create Redis script object
	tokenBucketScript = redis.NewScript(string(scriptContent))
	return nil
}

func rateLimitHandler(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	if userID == "" {
		http.Error(w, "user_id required", http.StatusBadRequest)
		return
	}

	// Redis key for this user's bucket
	key := fmt.Sprintf("ratelimit:%s", userID)

	// Current timestamp in seconds
	now := time.Now().Unix()

	// Execute the token bucket Lua script
	// KEYS[1]: Redis key
	// ARGV[1]: max tokens (bucket capacity)
	// ARGV[2]: refill rate (tokens per second)
	// ARGV[3]: tokens requested (usually 1)
	// ARGV[4]: current timestamp (in seconds)
	result, err := tokenBucketScript.Run(ctx, rdb, []string{key},
		bucketCapacity, refillRate, 1, now).Result()

	if err != nil {
		log.Printf("Error executing token bucket script: %v", err)
		http.Error(w, "internal server error", http.StatusInternalServerError)
		return
	}

	// The script returns a boolean (0 or 1)
	allowed := result.(int64) == 1

	if allowed {
		// Get current bucket state for response headers
		bucketData, err := rdb.HMGet(ctx, key, "tokens", "last").Result()
		if err != nil {
			log.Printf("Error getting bucket state: %v", err)
			// Continue with default values
		}

		// Parse current tokens for response header
		var remainingTokens int
		if len(bucketData) > 0 && bucketData[0] != nil {
			if tokens, err := strconv.ParseFloat(bucketData[0].(string), 64); err == nil {
				remainingTokens = int(tokens)
			}
		}

		// Calculate next refill time (approximate)
		nextRefillSeconds := int64(1.0 / refillRate)
		nextRefill := now + nextRefillSeconds

		// Set response headers for successful request
		w.Header().Set("X-RateLimit-Limit", strconv.Itoa(bucketCapacity))
		w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(remainingTokens))
		w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(nextRefill, 10))

		w.WriteHeader(http.StatusOK)
		w.Write([]byte("allowed"))
	} else {
		// Calculate retry after time
		retryAfterSeconds := int(1.0 / refillRate)

		// Set response headers for rate limit exceeded
		w.Header().Set("X-RateLimit-Limit", strconv.Itoa(bucketCapacity))
		w.Header().Set("X-RateLimit-Remaining", "0")
		w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(now+int64(retryAfterSeconds), 10))
		w.Header().Set("Retry-After", strconv.Itoa(retryAfterSeconds))

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
