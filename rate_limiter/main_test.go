package main

import (
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/go-redis/redismock/v8"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestRateLimitHandler_FirstRequest(t *testing.T) {
	// Setup mock Redis
	db, mock := redismock.NewClientMock()
	originalRdb := rdb
	rdb = db
	defer func() { rdb = originalRdb }()

	// Set test configuration
	originalCapacity := bucketCapacity
	originalInterval := refillInterval
	bucketCapacity = 5
	refillInterval = 10 * time.Second
	defer func() {
		bucketCapacity = originalCapacity
		refillInterval = originalInterval
	}()

	userID := "user123"
	keyTokens := "ratelimit:" + userID + ":tokens"
	keyTimestamp := "ratelimit:" + userID + ":ts"

	// Mock Redis responses for first request (no existing data)
	mock.ExpectGet(keyTokens).RedisNil()
	mock.ExpectGet(keyTimestamp).RedisNil()
	mock.ExpectSet(keyTokens, 4, refillInterval).SetVal("OK")
	mock.Regexp().ExpectSet(keyTimestamp, `\d+`, refillInterval).SetVal("OK")

	// Create request
	req := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w := httptest.NewRecorder()

	// Call handler
	rateLimitHandler(w, req)

	// Assertions
	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "allowed", w.Body.String())
	assert.Equal(t, "5", w.Header().Get("X-RateLimit-Limit"))
	assert.Equal(t, "4", w.Header().Get("X-RateLimit-Remaining"))

	// Verify all Redis expectations were met
	require.NoError(t, mock.ExpectationsWereMet())
}

func TestRateLimitHandler_SubsequentRequests(t *testing.T) {
	// Setup mock Redis
	db, mock := redismock.NewClientMock()
	originalRdb := rdb
	rdb = db
	defer func() { rdb = originalRdb }()

	// Set test configuration
	originalCapacity := bucketCapacity
	originalInterval := refillInterval
	bucketCapacity = 5
	refillInterval = 10 * time.Second
	defer func() {
		bucketCapacity = originalCapacity
		refillInterval = originalInterval
	}()

	userID := "user123"
	keyTokens := "ratelimit:" + userID + ":tokens"
	keyTimestamp := "ratelimit:" + userID + ":ts"
	now := time.Now().Unix()

	// Mock Redis responses for existing user with tokens
	mock.ExpectGet(keyTokens).SetVal("3")                           // 3 tokens remaining
	mock.ExpectGet(keyTimestamp).SetVal(strconv.FormatInt(now, 10)) // Recent timestamp
	mock.ExpectSet(keyTokens, 2, refillInterval).SetVal("OK")
	mock.ExpectSet(keyTimestamp, now, refillInterval).SetVal("OK")

	// Create request
	req := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w := httptest.NewRecorder()

	// Call handler
	rateLimitHandler(w, req)

	// Assertions
	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "allowed", w.Body.String())
	assert.Equal(t, "5", w.Header().Get("X-RateLimit-Limit"))
	assert.Equal(t, "2", w.Header().Get("X-RateLimit-Remaining"))

	// Verify all Redis expectations were met
	require.NoError(t, mock.ExpectationsWereMet())
}

func TestRateLimitHandler_ExceedsLimit(t *testing.T) {
	// Setup mock Redis
	db, mock := redismock.NewClientMock()
	originalRdb := rdb
	rdb = db
	defer func() { rdb = originalRdb }()

	// Set test configuration
	originalCapacity := bucketCapacity
	originalInterval := refillInterval
	bucketCapacity = 5
	refillInterval = 10 * time.Second
	defer func() {
		bucketCapacity = originalCapacity
		refillInterval = originalInterval
	}()

	userID := "user123"
	keyTokens := "ratelimit:" + userID + ":tokens"
	keyTimestamp := "ratelimit:" + userID + ":ts"
	now := time.Now().Unix()

	// Mock Redis responses for user with no tokens
	mock.ExpectGet(keyTokens).SetVal("0")                           // No tokens remaining
	mock.ExpectGet(keyTimestamp).SetVal(strconv.FormatInt(now, 10)) // Recent timestamp

	// Create request
	req := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w := httptest.NewRecorder()

	// Call handler
	rateLimitHandler(w, req)

	// Assertions
	assert.Equal(t, http.StatusTooManyRequests, w.Code)
	assert.Equal(t, "rate limit exceeded", w.Body.String())
	assert.Equal(t, "5", w.Header().Get("X-RateLimit-Limit"))
	assert.Equal(t, "0", w.Header().Get("X-RateLimit-Remaining"))
	assert.Equal(t, "10", w.Header().Get("Retry-After"))

	// Verify all Redis expectations were met
	require.NoError(t, mock.ExpectationsWereMet())
}

func TestRateLimitHandler_TokenRefill(t *testing.T) {
	// Setup mock Redis
	db, mock := redismock.NewClientMock()
	originalRdb := rdb
	rdb = db
	defer func() { rdb = originalRdb }()

	// Set test configuration
	originalCapacity := bucketCapacity
	originalInterval := refillInterval
	bucketCapacity = 5
	refillInterval = 10 * time.Second
	defer func() {
		bucketCapacity = originalCapacity
		refillInterval = originalInterval
	}()

	userID := "user123"
	keyTokens := "ratelimit:" + userID + ":tokens"
	keyTimestamp := "ratelimit:" + userID + ":ts"
	oldTimestamp := time.Now().Unix() - 15 // 15 seconds ago (older than refill interval)

	// Mock Redis responses for user with old timestamp (should refill)
	mock.ExpectGet(keyTokens).SetVal("0")                                    // No tokens remaining
	mock.ExpectGet(keyTimestamp).SetVal(strconv.FormatInt(oldTimestamp, 10)) // Old timestamp
	mock.ExpectSet(keyTokens, 4, refillInterval).SetVal("OK")                // Refilled to capacity-1
	mock.Regexp().ExpectSet(keyTimestamp, `\d+`, refillInterval).SetVal("OK")

	// Create request
	req := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w := httptest.NewRecorder()

	// Call handler
	rateLimitHandler(w, req)

	// Assertions
	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "allowed", w.Body.String())
	assert.Equal(t, "5", w.Header().Get("X-RateLimit-Limit"))
	assert.Equal(t, "4", w.Header().Get("X-RateLimit-Remaining"))

	// Verify all Redis expectations were met
	require.NoError(t, mock.ExpectationsWereMet())
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

func TestRateLimitHandler_EmptyUserID(t *testing.T) {
	// Create request with empty user_id parameter
	req := httptest.NewRequest("GET", "/check?user_id=", nil)
	w := httptest.NewRecorder()

	// Call handler
	rateLimitHandler(w, req)

	// Assertions
	assert.Equal(t, http.StatusBadRequest, w.Code)
	assert.Equal(t, "user_id required\n", w.Body.String())
}

func TestHealthHandler_Success(t *testing.T) {
	// Setup mock Redis
	db, mock := redismock.NewClientMock()
	originalRdb := rdb
	rdb = db
	defer func() { rdb = originalRdb }()

	// Mock successful Redis ping
	mock.ExpectPing().SetVal("PONG")

	// Create request
	req := httptest.NewRequest("GET", "/health", nil)
	w := httptest.NewRecorder()

	// Call handler
	healthHandler(w, req)

	// Assertions
	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "OK", w.Body.String())

	// Verify all Redis expectations were met
	require.NoError(t, mock.ExpectationsWereMet())
}

func TestHealthHandler_RedisFailure(t *testing.T) {
	// Setup mock Redis
	db, mock := redismock.NewClientMock()
	originalRdb := rdb
	rdb = db
	defer func() { rdb = originalRdb }()

	// Mock failed Redis ping
	mock.ExpectPing().SetErr(redis.Nil)

	// Create request
	req := httptest.NewRequest("GET", "/health", nil)
	w := httptest.NewRecorder()

	// Call handler
	healthHandler(w, req)

	// Assertions
	assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	assert.Equal(t, "Redis connection failed", w.Body.String())

	// Verify all Redis expectations were met
	require.NoError(t, mock.ExpectationsWereMet())
}

func TestRateLimitHandler_MultipleUsers(t *testing.T) {
	// Setup mock Redis
	db, mock := redismock.NewClientMock()
	originalRdb := rdb
	rdb = db
	defer func() { rdb = originalRdb }()

	// Set test configuration
	originalCapacity := bucketCapacity
	originalInterval := refillInterval
	bucketCapacity = 2
	refillInterval = 10 * time.Second
	defer func() {
		bucketCapacity = originalCapacity
		refillInterval = originalInterval
	}()

	user1 := "user1"
	user2 := "user2"

	// Mock Redis responses for first user (first request)
	mock.ExpectGet("ratelimit:" + user1 + ":tokens").RedisNil()
	mock.ExpectGet("ratelimit:" + user1 + ":ts").RedisNil()
	mock.ExpectSet("ratelimit:"+user1+":tokens", 1, refillInterval).SetVal("OK")
	mock.Regexp().ExpectSet("ratelimit:"+user1+":ts", `\d+`, refillInterval).SetVal("OK")

	// Mock Redis responses for second user (first request)
	mock.ExpectGet("ratelimit:" + user2 + ":tokens").RedisNil()
	mock.ExpectGet("ratelimit:" + user2 + ":ts").RedisNil()
	mock.ExpectSet("ratelimit:"+user2+":tokens", 1, refillInterval).SetVal("OK")
	mock.Regexp().ExpectSet("ratelimit:"+user2+":ts", `\d+`, refillInterval).SetVal("OK")

	// Test first user
	req1 := httptest.NewRequest("GET", "/check?user_id="+user1, nil)
	w1 := httptest.NewRecorder()
	rateLimitHandler(w1, req1)

	assert.Equal(t, http.StatusOK, w1.Code)
	assert.Equal(t, "allowed", w1.Body.String())
	assert.Equal(t, "1", w1.Header().Get("X-RateLimit-Remaining"))

	// Test second user (independent rate limit)
	req2 := httptest.NewRequest("GET", "/check?user_id="+user2, nil)
	w2 := httptest.NewRecorder()
	rateLimitHandler(w2, req2)

	assert.Equal(t, http.StatusOK, w2.Code)
	assert.Equal(t, "allowed", w2.Body.String())
	assert.Equal(t, "1", w2.Header().Get("X-RateLimit-Remaining"))

	// Verify all Redis expectations were met
	require.NoError(t, mock.ExpectationsWereMet())
}

func TestRateLimitHandler_InvalidTokensInRedis(t *testing.T) {
	// Setup mock Redis
	db, mock := redismock.NewClientMock()
	originalRdb := rdb
	rdb = db
	defer func() { rdb = originalRdb }()

	// Set test configuration
	originalCapacity := bucketCapacity
	originalInterval := refillInterval
	bucketCapacity = 5
	refillInterval = 10 * time.Second
	defer func() {
		bucketCapacity = originalCapacity
		refillInterval = originalInterval
	}()

	userID := "user123"
	keyTokens := "ratelimit:" + userID + ":tokens"
	keyTimestamp := "ratelimit:" + userID + ":ts"

	// Mock Redis responses with invalid token count (non-numeric)
	mock.ExpectGet(keyTokens).SetVal("invalid")
	mock.ExpectGet(keyTimestamp).SetVal("invalid")
	mock.ExpectSet(keyTokens, 4, refillInterval).SetVal("OK")
	mock.Regexp().ExpectSet(keyTimestamp, `\d+`, refillInterval).SetVal("OK")

	// Create request
	req := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w := httptest.NewRecorder()

	// Call handler
	rateLimitHandler(w, req)

	// Should handle invalid data gracefully and treat as new user
	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "allowed", w.Body.String())
	assert.Equal(t, "4", w.Header().Get("X-RateLimit-Remaining"))

	// Verify all Redis expectations were met
	require.NoError(t, mock.ExpectationsWereMet())
}

// Integration test to verify the complete rate limiting flow
func TestRateLimitHandler_CompleteFlow(t *testing.T) {
	// Setup mock Redis
	db, mock := redismock.NewClientMock()
	originalRdb := rdb
	rdb = db
	defer func() { rdb = originalRdb }()

	// Set test configuration
	originalCapacity := bucketCapacity
	originalInterval := refillInterval
	bucketCapacity = 3
	refillInterval = 10 * time.Second
	defer func() {
		bucketCapacity = originalCapacity
		refillInterval = originalInterval
	}()

	userID := "user123"
	keyTokens := "ratelimit:" + userID + ":tokens"
	keyTimestamp := "ratelimit:" + userID + ":ts"
	now := time.Now().Unix()

	// Request 1: First request (should be allowed)
	mock.ExpectGet(keyTokens).RedisNil()
	mock.ExpectGet(keyTimestamp).RedisNil()
	mock.ExpectSet(keyTokens, 2, refillInterval).SetVal("OK")
	mock.Regexp().ExpectSet(keyTimestamp, `\d+`, refillInterval).SetVal("OK")

	req1 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w1 := httptest.NewRecorder()
	rateLimitHandler(w1, req1)

	assert.Equal(t, http.StatusOK, w1.Code)
	assert.Equal(t, "2", w1.Header().Get("X-RateLimit-Remaining"))

	// Request 2: Second request (should be allowed)
	mock.ExpectGet(keyTokens).SetVal("2")
	mock.ExpectGet(keyTimestamp).SetVal(strconv.FormatInt(now, 10))
	mock.ExpectSet(keyTokens, 1, refillInterval).SetVal("OK")
	mock.ExpectSet(keyTimestamp, now, refillInterval).SetVal("OK")

	req2 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w2 := httptest.NewRecorder()
	rateLimitHandler(w2, req2)

	assert.Equal(t, http.StatusOK, w2.Code)
	assert.Equal(t, "1", w2.Header().Get("X-RateLimit-Remaining"))

	// Request 3: Third request (should be allowed)
	mock.ExpectGet(keyTokens).SetVal("1")
	mock.ExpectGet(keyTimestamp).SetVal(strconv.FormatInt(now, 10))
	mock.ExpectSet(keyTokens, 0, refillInterval).SetVal("OK")
	mock.ExpectSet(keyTimestamp, now, refillInterval).SetVal("OK")

	req3 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w3 := httptest.NewRecorder()
	rateLimitHandler(w3, req3)

	assert.Equal(t, http.StatusOK, w3.Code)
	assert.Equal(t, "0", w3.Header().Get("X-RateLimit-Remaining"))

	// Request 4: Fourth request (should be rate limited)
	mock.ExpectGet(keyTokens).SetVal("0")
	mock.ExpectGet(keyTimestamp).SetVal(strconv.FormatInt(now, 10))

	req4 := httptest.NewRequest("GET", "/check?user_id="+userID, nil)
	w4 := httptest.NewRecorder()
	rateLimitHandler(w4, req4)

	assert.Equal(t, http.StatusTooManyRequests, w4.Code)
	assert.Equal(t, "0", w4.Header().Get("X-RateLimit-Remaining"))

	// Verify all Redis expectations were met
	require.NoError(t, mock.ExpectationsWereMet())
}
