package main

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-redis/redis/v8"
	"github.com/stretchr/testify/assert"
)

func TestRateLimitHandler_MissingUserID(t *testing.T) {
	// Create request without user_id parameter
	req := httptest.NewRequest("GET", "/check", nil)
	w := httptest.NewRecorder()

	// Call handler
	rateLimitHandler(w, req)

	// Assertions
	assert.Equal(t, http.StatusBadRequest, w.Code)
	assert.Equal(t, "user_id required\n", w.Body.String())
}

func TestHealthHandler_Success(t *testing.T) {
	// This test requires a running Redis instance
	// Skip if Redis is not available
	originalRdb := rdb
	defer func() { rdb = originalRdb }()

	// Try to connect to Redis
	testClient := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
		DB:   1, // Use different DB for testing
	})

	// Test if Redis is available
	_, err := testClient.Ping(ctx).Result()
	if err != nil {
		t.Skip("Redis not available, skipping test")
		return
	}

	rdb = testClient
	defer testClient.Close()

	// Create request
	req := httptest.NewRequest("GET", "/health", nil)
	w := httptest.NewRecorder()

	// Call handler
	healthHandler(w, req)

	// Assertions
	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "OK", w.Body.String())
}

func TestHealthHandler_RedisFailure(t *testing.T) {
	// Save original
	originalRdb := rdb
	defer func() { rdb = originalRdb }()

	// Set up client with invalid address
	rdb = redis.NewClient(&redis.Options{
		Addr: "invalid:6379",
	})

	// Create request
	req := httptest.NewRequest("GET", "/health", nil)
	w := httptest.NewRecorder()

	// Call handler
	healthHandler(w, req)

	// Assertions
	assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	assert.Equal(t, "Redis connection failed", w.Body.String())
}

// TestRateLimitIntegration tests the complete rate limiting functionality
// This requires Redis to be running on localhost:6379
func TestRateLimitIntegration(t *testing.T) {
	// Save original values
	originalRdb := rdb
	originalScript := tokenBucketScript
	originalCapacity := bucketCapacity
	originalRate := refillRate

	defer func() {
		rdb = originalRdb
		tokenBucketScript = originalScript
		bucketCapacity = originalCapacity
		refillRate = originalRate
	}()

	// Set up test configuration
	bucketCapacity = 2
	refillRate = 1.0 // 1 token per second

	// Try to connect to Redis
	testClient := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
		DB:   1, // Use different DB for testing
	})

	// Test if Redis is available
	_, err := testClient.Ping(ctx).Result()
	if err != nil {
		t.Skip("Redis not available, skipping integration test")
		return
	}

	rdb = testClient
	defer testClient.Close()

	// Load the Lua script
	err = loadTokenBucketScript()
	if err != nil {
		t.Fatalf("Failed to load token bucket script: %v", err)
	}

	userID := "test_user_123"

	// Clean up any existing state
	key := "ratelimit:" + userID
	rdb.Del(ctx, key)

	// Test 1: First request should be allowed
	req1 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w1 := httptest.NewRecorder()
	rateLimitHandler(w1, req1)

	assert.Equal(t, http.StatusOK, w1.Code)
	assert.Equal(t, "allowed", w1.Body.String())
	assert.Equal(t, "2", w1.Header().Get("X-RateLimit-Limit"))

	// Test 2: Second request should be allowed
	req2 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w2 := httptest.NewRecorder()
	rateLimitHandler(w2, req2)

	assert.Equal(t, http.StatusOK, w2.Code)
	assert.Equal(t, "allowed", w2.Body.String())
	assert.Equal(t, "2", w2.Header().Get("X-RateLimit-Limit"))

	// Test 3: Third request should be rate limited
	req3 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w3 := httptest.NewRecorder()
	rateLimitHandler(w3, req3)

	assert.Equal(t, http.StatusTooManyRequests, w3.Code)
	assert.Equal(t, "rate limit exceeded", w3.Body.String())
	assert.Equal(t, "2", w3.Header().Get("X-RateLimit-Limit"))
	assert.Equal(t, "0", w3.Header().Get("X-RateLimit-Remaining"))
	assert.Equal(t, "1", w3.Header().Get("Retry-After"))

	// Clean up
	rdb.Del(ctx, key)

	t.Logf("Integration test completed successfully")
}
