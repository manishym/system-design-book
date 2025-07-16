package main

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-redis/redis/v8"
	"github.com/stretchr/testify/assert"
)

func setupTestEnvironment(t *testing.T, algo string) func() {
	// Save original values
	originalRdb := rdb
	originalScript := rateLimitScript
	originalCapacity := bucketCapacity
	originalRate := rate
	originalAlgorithm := algorithm

	// Set test configuration
	bucketCapacity = 5
	rate = 0.1 // 1 token every 10 seconds for token bucket, leak 0.1 requests/sec for leaky bucket
	algorithm = algo

	// Try to connect to Redis
	testClient := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
		DB:   1, // Use different DB for testing
	})

	// Test if Redis is available
	_, err := testClient.Ping(ctx).Result()
	if err != nil {
		t.Skip("Redis not available, skipping test")
		return func() {}
	}

	rdb = testClient

	// Load the appropriate script
	err = loadRateLimitScript()
	if err != nil {
		t.Fatalf("Failed to load %s bucket script: %v", algorithm, err)
	}

	cleanup := func() {
		testClient.Close()
		rdb = originalRdb
		rateLimitScript = originalScript
		bucketCapacity = originalCapacity
		rate = originalRate
		algorithm = originalAlgorithm
	}

	return cleanup
}

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

// TestTokenBucketIntegration tests the complete token bucket functionality
func TestTokenBucketIntegration(t *testing.T) {
	cleanup := setupTestEnvironment(t, "token")
	defer cleanup()

	// Set up test configuration
	bucketCapacity = 2
	rate = 1.0 // 1 token per second

	userID := "test_token_user"

	// Clean up any existing state
	key := "ratelimit:token:" + userID
	rdb.Del(ctx, key)

	// Test 1: First request should be allowed
	req1 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w1 := httptest.NewRecorder()
	rateLimitHandler(w1, req1)

	assert.Equal(t, http.StatusOK, w1.Code)
	assert.Equal(t, "allowed", w1.Body.String())
	assert.Equal(t, "2", w1.Header().Get("X-RateLimit-Limit"))
	assert.Equal(t, "token bucket", w1.Header().Get("X-RateLimit-Algorithm"))

	// Test 2: Second request should be allowed
	req2 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w2 := httptest.NewRecorder()
	rateLimitHandler(w2, req2)

	assert.Equal(t, http.StatusOK, w2.Code)
	assert.Equal(t, "allowed", w2.Body.String())

	// Test 3: Third request should be rate limited (bucket exhausted)
	req3 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w3 := httptest.NewRecorder()
	rateLimitHandler(w3, req3)

	assert.Equal(t, http.StatusTooManyRequests, w3.Code)
	assert.Equal(t, "rate limit exceeded", w3.Body.String())
	assert.Equal(t, "2", w3.Header().Get("X-RateLimit-Limit"))
	assert.Equal(t, "0", w3.Header().Get("X-RateLimit-Remaining"))
	assert.Equal(t, "1", w3.Header().Get("Retry-After"))
	assert.Equal(t, "token bucket", w3.Header().Get("X-RateLimit-Algorithm"))

	// Clean up
	rdb.Del(ctx, key)

	t.Logf("Token bucket integration test completed successfully")
}

// TestLeakyBucketIntegration tests the complete leaky bucket functionality
func TestLeakyBucketIntegration(t *testing.T) {
	cleanup := setupTestEnvironment(t, "leaky")
	defer cleanup()

	// Set up test configuration
	bucketCapacity = 2
	rate = 1.0 // leak 1 request per second

	userID := "test_leaky_user"

	// Clean up any existing state
	key := "ratelimit:leaky:" + userID
	rdb.Del(ctx, key)

	// Test 1: First request should be allowed
	req1 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w1 := httptest.NewRecorder()
	rateLimitHandler(w1, req1)

	assert.Equal(t, http.StatusOK, w1.Code)
	assert.Equal(t, "allowed", w1.Body.String())
	assert.Equal(t, "2", w1.Header().Get("X-RateLimit-Limit"))
	assert.Equal(t, "leaky bucket", w1.Header().Get("X-RateLimit-Algorithm"))

	// Test 2: Second request should be allowed
	req2 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w2 := httptest.NewRecorder()
	rateLimitHandler(w2, req2)

	assert.Equal(t, http.StatusOK, w2.Code)
	assert.Equal(t, "allowed", w2.Body.String())

	// Test 3: Third request should be rate limited (bucket full)
	req3 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w3 := httptest.NewRecorder()
	rateLimitHandler(w3, req3)

	assert.Equal(t, http.StatusTooManyRequests, w3.Code)
	assert.Equal(t, "rate limit exceeded", w3.Body.String())
	assert.Equal(t, "2", w3.Header().Get("X-RateLimit-Limit"))
	assert.Equal(t, "0", w3.Header().Get("X-RateLimit-Remaining"))
	assert.Equal(t, "1", w3.Header().Get("Retry-After"))
	assert.Equal(t, "leaky bucket", w3.Header().Get("X-RateLimit-Algorithm"))

	// Clean up
	rdb.Del(ctx, key)

	t.Logf("Leaky bucket integration test completed successfully")
}

// TestAlgorithmIsolation ensures token and leaky buckets are isolated from each other
func TestAlgorithmIsolation(t *testing.T) {
	// Test token bucket first
	cleanup1 := setupTestEnvironment(t, "token")
	defer cleanup1()

	userID := "isolation_test_user"
	bucketCapacity = 1
	rate = 1.0

	// Use up token bucket
	req1 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w1 := httptest.NewRecorder()
	rateLimitHandler(w1, req1)
	assert.Equal(t, http.StatusOK, w1.Code)

	req2 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w2 := httptest.NewRecorder()
	rateLimitHandler(w2, req2)
	assert.Equal(t, http.StatusTooManyRequests, w2.Code) // Token bucket exhausted

	// Switch to leaky bucket
	cleanup2 := setupTestEnvironment(t, "leaky")
	defer cleanup2()

	// Leaky bucket should start fresh (different Redis key)
	req3 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w3 := httptest.NewRecorder()
	rateLimitHandler(w3, req3)
	assert.Equal(t, http.StatusOK, w3.Code) // Leaky bucket allows request

	t.Logf("Algorithm isolation test completed successfully")
}
