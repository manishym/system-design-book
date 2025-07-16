package main

import (
	"context"
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"strconv"
	"strings"
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
	rate           float64 // tokens per second for token bucket, leak rate for leaky bucket
	algorithm      string  // "token" or "leaky"
	serverPort     string
)

var rdb *redis.Client
var rateLimitScript *redis.Script

func init() {
	// Define command line flags with default values
	flag.StringVar(&redisAddr, "redis-addr", "redis-master:6379", "Redis server address")
	flag.StringVar(&redisPassword, "redis-password", "", "Redis password")
	flag.IntVar(&redisDB, "redis-db", 0, "Redis database number")
	flag.IntVar(&bucketCapacity, "bucket-capacity", 5, "Bucket capacity (max tokens for token bucket, max requests for leaky bucket)")
	flag.Float64Var(&rate, "rate", 1, "Rate (tokens per second for token bucket, leak rate for leaky bucket)")
	flag.StringVar(&algorithm, "algorithm", "leaky", "Rate limiting algorithm: 'token' or 'leaky'")
	flag.StringVar(&serverPort, "port", "8080", "Server port")
}

func main() {
	// Parse command line flags
	flag.Parse()

	// Validate algorithm
	algorithm = strings.ToLower(algorithm)
	if algorithm != "token" && algorithm != "leaky" {
		log.Fatalf("Invalid algorithm '%s'. Must be 'token' or 'leaky'", algorithm)
	}

	// Log configuration
	log.Printf("Starting rate limiter with config:")
	log.Printf("  Algorithm: %s bucket", algorithm)
	log.Printf("  Redis Address: %s", redisAddr)
	log.Printf("  Redis DB: %d", redisDB)
	log.Printf("  Bucket Capacity: %d", bucketCapacity)
	if algorithm == "token" {
		log.Printf("  Refill Rate: %.2f tokens/second", rate)
	} else {
		log.Printf("  Leak Rate: %.2f requests/second", rate)
	}
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

	// Load the appropriate Lua script
	err = loadRateLimitScript()
	if err != nil {
		log.Fatalf("Failed to load rate limiting script: %v", err)
	}
	log.Printf("Successfully loaded %s bucket Lua script", algorithm)

	// Setup HTTP handlers
	http.HandleFunc("/check", rateLimitHandler)
	http.HandleFunc("/health", healthHandler)

	log.Printf("Rate limiter running on port %s", serverPort)
	log.Fatal(http.ListenAndServe(":"+serverPort, nil))
}

func loadRateLimitScript() error {
	var scriptFile string
	if algorithm == "token" {
		scriptFile = "token_bucket.lua"
	} else {
		scriptFile = "leaky_bucket.lua"
	}

	// Read the Lua script from file
	scriptContent, err := ioutil.ReadFile(scriptFile)
	if err != nil {
		return fmt.Errorf("failed to read %s: %w", scriptFile, err)
	}

	// Create Redis script object
	rateLimitScript = redis.NewScript(string(scriptContent))
	return nil
}

func rateLimitHandler(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	if userID == "" {
		http.Error(w, "user_id required", http.StatusBadRequest)
		return
	}

	// Redis key for this user's bucket
	key := fmt.Sprintf("ratelimit:%s:%s", algorithm, userID)

	// Current timestamp in seconds
	now := time.Now().Unix()

	// Execute the rate limiting Lua script
	// Both scripts use the same parameters:
	// KEYS[1]: Redis key
	// ARGV[1]: bucket capacity
	// ARGV[2]: rate (refill rate for token bucket, leak rate for leaky bucket)
	// ARGV[3]: requests (usually 1)
	// ARGV[4]: current timestamp (in seconds)
	result, err := rateLimitScript.Run(ctx, rdb, []string{key},
		bucketCapacity, rate, 1, now).Result()

	if err != nil {
		log.Printf("Error executing %s bucket script: %v", algorithm, err)
		http.Error(w, "internal server error", http.StatusInternalServerError)
		return
	}

	// The script returns 1 for allowed, 0 for denied
	allowed := result.(int64) == 1

	if allowed {
		// Get current bucket state for response headers
		var stateFields []string
		if algorithm == "token" {
			stateFields = []string{"tokens", "last"}
		} else {
			stateFields = []string{"volume", "last_leak"}
		}

		bucketData, err := rdb.HMGet(ctx, key, stateFields...).Result()
		if err != nil {
			log.Printf("Error getting bucket state: %v", err)
			// Continue with default values
		}

		// Parse current state for response header
		var remaining int
		if len(bucketData) > 0 && bucketData[0] != nil {
			if algorithm == "token" {
				// For token bucket, remaining = tokens left
				if tokens, err := strconv.ParseFloat(bucketData[0].(string), 64); err == nil {
					remaining = int(tokens)
				}
			} else {
				// For leaky bucket, remaining = capacity - current volume
				if volume, err := strconv.ParseFloat(bucketData[0].(string), 64); err == nil {
					remaining = bucketCapacity - int(volume)
				}
			}
		}

		// Calculate next available time (approximate)
		nextAvailableSeconds := int64(1.0 / rate)
		nextAvailable := now + nextAvailableSeconds

		// Set response headers for successful request
		w.Header().Set("X-RateLimit-Limit", strconv.Itoa(bucketCapacity))
		w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(remaining))
		w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(nextAvailable, 10))
		w.Header().Set("X-RateLimit-Algorithm", algorithm+" bucket")

		w.WriteHeader(http.StatusOK)
		w.Write([]byte("allowed"))
	} else {
		// Calculate retry after time
		retryAfterSeconds := int(1.0 / rate)

		// Set response headers for rate limit exceeded
		w.Header().Set("X-RateLimit-Limit", strconv.Itoa(bucketCapacity))
		w.Header().Set("X-RateLimit-Remaining", "0")
		w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(now+int64(retryAfterSeconds), 10))
		w.Header().Set("X-RateLimit-Algorithm", algorithm+" bucket")
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
