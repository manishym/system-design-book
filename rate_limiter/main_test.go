package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

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

// TestMultiUserTokenBucket tests multi-user functionality with token bucket
func TestMultiUserTokenBucket(t *testing.T) {
	cleanup := setupTestEnvironment(t, "token")
	defer cleanup()

	bucketCapacity = 2
	rate = 1.0

	userA := "user_a"
	userB := "user_b"

	// Clean up any existing state
	keyA := "ratelimit:token:" + userA
	keyB := "ratelimit:token:" + userB
	rdb.Del(ctx, keyA, keyB)
	rdb.Del(ctx, "ratelimit:users:"+userA, "ratelimit:users:"+userB)
	rdb.SRem(ctx, "ratelimit:users", userA, userB)

	// Test 1: User A makes requests (should auto-create with defaults)
	req1 := httptest.NewRequest("GET", "/check?user_id="+userA, nil)
	w1 := httptest.NewRecorder()
	rateLimitHandler(w1, req1)

	assert.Equal(t, http.StatusOK, w1.Code)
	assert.Equal(t, "allowed", w1.Body.String())

	// Verify user A was created
	exists := rdb.SIsMember(ctx, "ratelimit:users", userA).Val()
	assert.True(t, exists, "User A should be added to users set")

	// Test 2: User B makes requests (independent bucket)
	req2 := httptest.NewRequest("GET", "/check?user_id="+userB, nil)
	w2 := httptest.NewRecorder()
	rateLimitHandler(w2, req2)

	assert.Equal(t, http.StatusOK, w2.Code)
	assert.Equal(t, "allowed", w2.Body.String())

	// Test 3: Exhaust User A's bucket
	req3 := httptest.NewRequest("GET", "/check?user_id="+userA, nil)
	w3 := httptest.NewRecorder()
	rateLimitHandler(w3, req3)

	assert.Equal(t, http.StatusOK, w3.Code) // Second request for user A

	req4 := httptest.NewRequest("GET", "/check?user_id="+userA, nil)
	w4 := httptest.NewRecorder()
	rateLimitHandler(w4, req4)

	assert.Equal(t, http.StatusTooManyRequests, w4.Code) // User A exhausted

	// Test 4: User B should still have tokens available
	req5 := httptest.NewRequest("GET", "/check?user_id="+userB, nil)
	w5 := httptest.NewRecorder()
	rateLimitHandler(w5, req5)

	assert.Equal(t, http.StatusOK, w5.Code) // User B still has tokens

	// Clean up
	rdb.Del(ctx, keyA, keyB)
	rdb.Del(ctx, "ratelimit:users:"+userA, "ratelimit:users:"+userB)
	rdb.SRem(ctx, "ratelimit:users", userA, userB)

	t.Logf("Multi-user token bucket test completed successfully")
}

// TestMultiUserLeakyBucket tests multi-user functionality with leaky bucket
func TestMultiUserLeakyBucket(t *testing.T) {
	cleanup := setupTestEnvironment(t, "leaky")
	defer cleanup()

	bucketCapacity = 2
	rate = 1.0

	userA := "user_a_leaky"
	userB := "user_b_leaky"

	// Clean up any existing state more thoroughly
	keyA := "ratelimit:leaky:" + userA
	keyB := "ratelimit:leaky:" + userB

	// Multiple cleanup attempts to handle CI timing issues
	for i := 0; i < 3; i++ {
		rdb.Del(ctx, keyA, keyB)
		rdb.Del(ctx, "ratelimit:users:"+userA, "ratelimit:users:"+userB)
		rdb.SRem(ctx, "ratelimit:users", userA, userB)
		// Small delay to ensure cleanup completes
		if i < 2 {
			time.Sleep(10 * time.Millisecond)
		}
	}

	// Test 1: User A fills bucket (capacity=2)
	req1 := httptest.NewRequest("GET", "/check?user_id="+userA, nil)
	w1 := httptest.NewRecorder()
	rateLimitHandler(w1, req1)
	assert.Equal(t, http.StatusOK, w1.Code, "First request should be allowed")

	req2 := httptest.NewRequest("GET", "/check?user_id="+userA, nil)
	w2 := httptest.NewRecorder()
	rateLimitHandler(w2, req2)
	assert.Equal(t, http.StatusOK, w2.Code, "Second request should be allowed")

	// User A bucket should be full now (capacity=2, so 3rd request should be denied)
	req3 := httptest.NewRequest("GET", "/check?user_id="+userA, nil)
	w3 := httptest.NewRecorder()
	rateLimitHandler(w3, req3)

	// This is the critical assertion that was failing in CI
	assert.Equal(t, http.StatusTooManyRequests, w3.Code,
		"Third request should be denied when bucket is at capacity (capacity=%d)", bucketCapacity)

	// Test 2: User B should have independent bucket
	req4 := httptest.NewRequest("GET", "/check?user_id="+userB, nil)
	w4 := httptest.NewRecorder()
	rateLimitHandler(w4, req4)
	assert.Equal(t, http.StatusOK, w4.Code)

	req5 := httptest.NewRequest("GET", "/check?user_id="+userB, nil)
	w5 := httptest.NewRecorder()
	rateLimitHandler(w5, req5)
	assert.Equal(t, http.StatusOK, w5.Code)

	// Clean up
	rdb.Del(ctx, keyA, keyB)
	rdb.Del(ctx, "ratelimit:users:"+userA, "ratelimit:users:"+userB)
	rdb.SRem(ctx, "ratelimit:users", userA, userB)

	t.Logf("Multi-user leaky bucket test completed successfully")
}

// TestUserManagementEndpoints tests the user management API
func TestUserManagementEndpoints(t *testing.T) {
	cleanup := setupTestEnvironment(t, "token")
	defer cleanup()

	userID := "test_user_mgmt"

	// Clean up any existing state
	rdb.Del(ctx, "ratelimit:users:"+userID)
	rdb.SRem(ctx, "ratelimit:users", userID)

	// Test 1: GET non-existent user
	req1 := httptest.NewRequest("GET", "/users?user_id="+userID, nil)
	w1 := httptest.NewRecorder()
	userManagementHandler(w1, req1)

	assert.Equal(t, http.StatusNotFound, w1.Code)
	assert.Equal(t, "User not found", w1.Body.String())

	// Test 2: Create user by making a rate limit check
	req2 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w2 := httptest.NewRecorder()
	rateLimitHandler(w2, req2)

	assert.Equal(t, http.StatusOK, w2.Code)

	// Test 3: GET existing user
	req3 := httptest.NewRequest("GET", "/users?user_id="+userID, nil)
	w3 := httptest.NewRecorder()
	userManagementHandler(w3, req3)

	assert.Equal(t, http.StatusOK, w3.Code)
	assert.Contains(t, w3.Body.String(), userID)
	assert.Contains(t, w3.Body.String(), "token")

	// Test 4: POST update user limits
	req4 := httptest.NewRequest("POST", "/users?user_id="+userID+"&max_tokens=10&refill_rate=2", nil)
	w4 := httptest.NewRecorder()
	userManagementHandler(w4, req4)

	assert.Equal(t, http.StatusOK, w4.Code)
	assert.Equal(t, "User limits updated successfully", w4.Body.String())

	// Test 5: Verify updated limits
	req5 := httptest.NewRequest("GET", "/users?user_id="+userID, nil)
	w5 := httptest.NewRecorder()
	userManagementHandler(w5, req5)

	assert.Equal(t, http.StatusOK, w5.Code)
	assert.Contains(t, w5.Body.String(), "10") // max_tokens
	assert.Contains(t, w5.Body.String(), "2")  // refill_rate

	// Test 6: DELETE user
	req6 := httptest.NewRequest("DELETE", "/users?user_id="+userID, nil)
	w6 := httptest.NewRecorder()
	userManagementHandler(w6, req6)

	assert.Equal(t, http.StatusOK, w6.Code)
	assert.Equal(t, "User deleted successfully", w6.Body.String())

	// Test 7: Verify user is deleted
	req7 := httptest.NewRequest("GET", "/users?user_id="+userID, nil)
	w7 := httptest.NewRecorder()
	userManagementHandler(w7, req7)

	assert.Equal(t, http.StatusNotFound, w7.Code)

	t.Logf("User management endpoints test completed successfully")
}

// TestCustomUserLimits tests that custom user limits work correctly
func TestCustomUserLimits(t *testing.T) {
	cleanup := setupTestEnvironment(t, "token")
	defer cleanup()

	userID := "custom_limits_user"

	// Clean up any existing state
	rdb.Del(ctx, "ratelimit:token:"+userID)
	rdb.Del(ctx, "ratelimit:users:"+userID)
	rdb.SRem(ctx, "ratelimit:users", userID)

	// Test 1: Set custom limits for user (higher than default)
	req1 := httptest.NewRequest("POST", "/users?user_id="+userID+"&max_tokens=10&refill_rate=5", nil)
	w1 := httptest.NewRecorder()
	userManagementHandler(w1, req1)

	assert.Equal(t, http.StatusOK, w1.Code)

	// Test 2: User should now have custom limits
	// Make multiple requests that would exceed default limits but stay within custom limits
	allowedCount := 0
	for i := 0; i < 8; i++ { // 8 requests, default is 2, custom is 10
		req := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
		w := httptest.NewRecorder()
		rateLimitHandler(w, req)

		if w.Code == http.StatusOK {
			allowedCount++
		}
	}

	// Should allow more than default capacity (2) but less than custom capacity (10)
	assert.Greater(t, allowedCount, 2, "Should allow more than default capacity")
	assert.LessOrEqual(t, allowedCount, 10, "Should not exceed custom capacity")

	// Clean up
	rdb.Del(ctx, "ratelimit:token:"+userID)
	rdb.Del(ctx, "ratelimit:users:"+userID)
	rdb.SRem(ctx, "ratelimit:users", userID)

	t.Logf("Custom user limits test completed successfully")
}

// TestUserManagementErrorCases tests error conditions in user management
func TestUserManagementErrorCases(t *testing.T) {
	cleanup := setupTestEnvironment(t, "token")
	defer cleanup()

	// Test 1: Missing user_id in GET
	req1 := httptest.NewRequest("GET", "/users", nil)
	w1 := httptest.NewRecorder()
	userManagementHandler(w1, req1)

	assert.Equal(t, http.StatusBadRequest, w1.Code)
	assert.Equal(t, "user_id required\n", w1.Body.String())

	// Test 2: Missing user_id in POST
	req2 := httptest.NewRequest("POST", "/users?max_tokens=10", nil)
	w2 := httptest.NewRecorder()
	userManagementHandler(w2, req2)

	assert.Equal(t, http.StatusBadRequest, w2.Code)

	// Test 3: Invalid max_tokens in POST
	req3 := httptest.NewRequest("POST", "/users?user_id=test&max_tokens=invalid", nil)
	w3 := httptest.NewRecorder()
	userManagementHandler(w3, req3)

	assert.Equal(t, http.StatusBadRequest, w3.Code)
	assert.Equal(t, "invalid max_tokens\n", w3.Body.String())

	// Test 4: Invalid refill_rate in POST
	req4 := httptest.NewRequest("POST", "/users?user_id=test&refill_rate=invalid", nil)
	w4 := httptest.NewRecorder()
	userManagementHandler(w4, req4)

	assert.Equal(t, http.StatusBadRequest, w4.Code)
	assert.Equal(t, "invalid refill_rate\n", w4.Body.String())

	// Test 5: Unsupported HTTP method
	req5 := httptest.NewRequest("PUT", "/users?user_id=test", nil)
	w5 := httptest.NewRecorder()
	userManagementHandler(w5, req5)

	assert.Equal(t, http.StatusMethodNotAllowed, w5.Code)

	t.Logf("User management error cases test completed successfully")
}

// TestLeakyBucketUserManagement tests user management with leaky bucket algorithm
func TestLeakyBucketUserManagement(t *testing.T) {
	cleanup := setupTestEnvironment(t, "leaky")
	defer cleanup()

	userID := "leaky_user_mgmt"

	// Clean up any existing state
	rdb.Del(ctx, "ratelimit:users:"+userID)
	rdb.SRem(ctx, "ratelimit:users", userID)

	// Test 1: Create user through rate limiting
	req1 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w1 := httptest.NewRecorder()
	rateLimitHandler(w1, req1)

	assert.Equal(t, http.StatusOK, w1.Code)

	// Test 2: Update user with leaky bucket parameters
	req2 := httptest.NewRequest("POST", "/users?user_id="+userID+"&capacity=5&leak_rate=2", nil)
	w2 := httptest.NewRecorder()
	userManagementHandler(w2, req2)

	assert.Equal(t, http.StatusOK, w2.Code)

	// Test 3: Get user info should show leaky bucket parameters
	req3 := httptest.NewRequest("GET", "/users?user_id="+userID, nil)
	w3 := httptest.NewRecorder()
	userManagementHandler(w3, req3)

	assert.Equal(t, http.StatusOK, w3.Code)
	assert.Contains(t, w3.Body.String(), "leaky")
	assert.Contains(t, w3.Body.String(), "5") // capacity
	assert.Contains(t, w3.Body.String(), "2") // leak_rate

	// Clean up
	rdb.Del(ctx, "ratelimit:users:"+userID)
	rdb.SRem(ctx, "ratelimit:users", userID)

	t.Logf("Leaky bucket user management test completed successfully")
}
