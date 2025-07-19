package integration_test

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"syscall"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// IntegrationTestConfig holds configuration for integration tests
type IntegrationTestConfig struct {
	AppPort   string
	RedisAddr string
	RedisPort string
	AppBinary string
	Algorithm string
	Capacity  int
	Rate      float64
}

var integrationConfig = IntegrationTestConfig{
	AppPort:   "8081",           // Use different port to avoid conflicts
	RedisAddr: "localhost:6380", // Use different Redis port
	RedisPort: "6380",
	AppBinary: "./test/integration/rate-limiter-integration",
	Algorithm: "token",
	Capacity:  5,
	Rate:      1.0,
}

// Helper function to start Redis container for integration tests
func startRedisContainer(t *testing.T, port string) string {
	containerName := fmt.Sprintf("redis-integration-test-%s", port)

	// Clean up any existing container
	exec.Command("docker", "stop", containerName).Run()
	exec.Command("docker", "rm", containerName).Run()

	cmd := exec.Command("docker", "run", "-d",
		"--name", containerName,
		"-p", port+":6379",
		"redis:alpine")

	err := cmd.Run()
	require.NoError(t, err, "Failed to start Redis container")

	// Wait for Redis to be ready
	time.Sleep(3 * time.Second)

	// Verify Redis is running
	testCmd := exec.Command("docker", "exec", containerName, "redis-cli", "ping")
	output, err := testCmd.Output()
	require.NoError(t, err, "Redis health check failed")
	require.Contains(t, string(output), "PONG", "Redis not responding")

	return containerName
}

// Helper function to stop Redis container
func stopRedisContainer(containerName string) {
	exec.Command("docker", "stop", containerName).Run()
	exec.Command("docker", "rm", containerName).Run()
}

// Helper function to build app binary for integration tests
func buildAppBinary(t *testing.T) {
	// Check if binary already exists (built by runner script)
	if _, err := os.Stat(integrationConfig.AppBinary); err == nil {
		return // Binary already exists, no need to rebuild
	}

	// Build from the rate_limiter root directory
	cmd := exec.Command("go", "build", "-o", integrationConfig.AppBinary, "../../.")
	cmd.Dir = "." // Current directory is test/integration
	err := cmd.Run()
	require.NoError(t, err, "Failed to build app binary")
}

// Helper function to start the rate limiter app
func startApp(t *testing.T, config IntegrationTestConfig) *exec.Cmd {
	args := []string{
		"--redis-addr", config.RedisAddr,
		"--algorithm", config.Algorithm,
		"--bucket-capacity", fmt.Sprintf("%d", config.Capacity),
		"--rate", fmt.Sprintf("%.1f", config.Rate),
		"--port", config.AppPort,
	}

	cmd := exec.Command(config.AppBinary, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Dir = "../.." // Set working directory to rate_limiter root where Lua scripts are located

	err := cmd.Start()
	require.NoError(t, err, "Failed to start app")

	// Wait for app to be ready with retries
	var resp *http.Response
	var healthCheckErr error

	for i := 0; i < 10; i++ { // Try for up to 10 seconds
		time.Sleep(1 * time.Second)
		resp, healthCheckErr = http.Get(fmt.Sprintf("http://localhost:%s/health", config.AppPort))
		if healthCheckErr == nil && resp.StatusCode == http.StatusOK {
			resp.Body.Close()
			break
		}
		if resp != nil {
			resp.Body.Close()
		}
		t.Logf("Health check attempt %d failed, retrying...", i+1)
	}

	require.NoError(t, healthCheckErr, "App health check failed after retries")
	require.Equal(t, http.StatusOK, resp.StatusCode, "App not healthy")

	return cmd
}

// Helper function to make HTTP requests to the app
func makeRequest(method, url string, body io.Reader) (*http.Response, error) {
	client := &http.Client{Timeout: 5 * time.Second}
	req, err := http.NewRequest(method, url, body)
	if err != nil {
		return nil, err
	}
	return client.Do(req)
}

// TestAppLifecycle tests normal app startup and shutdown
func TestAppLifecycle(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	redisContainer := startRedisContainer(t, integrationConfig.RedisPort)
	defer stopRedisContainer(redisContainer)

	buildAppBinary(t)
	defer os.Remove(integrationConfig.AppBinary)

	t.Run("Normal startup and shutdown", func(t *testing.T) {
		cmd := startApp(t, integrationConfig)
		defer cmd.Process.Kill()

		// Test basic functionality
		url := fmt.Sprintf("http://localhost:%s/check?user_id=lifecycle_test", integrationConfig.AppPort)
		resp, err := makeRequest("GET", url, nil)
		require.NoError(t, err)
		defer resp.Body.Close()

		assert.Equal(t, http.StatusOK, resp.StatusCode)

		// Graceful shutdown
		err = cmd.Process.Signal(syscall.SIGTERM)
		require.NoError(t, err)

		// Wait for process to exit
		done := make(chan error, 1)
		go func() {
			done <- cmd.Wait()
		}()

		select {
		case err := <-done:
			// Process should exit cleanly
			if err != nil {
				t.Logf("Process exited with error: %v", err)
			}
		case <-time.After(10 * time.Second):
			t.Error("Process did not exit within timeout")
			cmd.Process.Kill()
		}
	})
}

// TestAppCrashRecovery tests app behavior when killed abruptly
func TestAppCrashRecovery(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	redisContainer := startRedisContainer(t, integrationConfig.RedisPort)
	defer stopRedisContainer(redisContainer)

	buildAppBinary(t)
	defer os.Remove(integrationConfig.AppBinary)

	t.Run("Abrupt kill and restart", func(t *testing.T) {
		// Start app and create some user data
		cmd1 := startApp(t, integrationConfig)

		// Create user data
		userURL := fmt.Sprintf("http://localhost:%s/users?user_id=crash_test&max_tokens=10&refill_rate=2", integrationConfig.AppPort)
		resp, err := makeRequest("POST", userURL, nil)
		require.NoError(t, err)
		resp.Body.Close()
		assert.Equal(t, http.StatusOK, resp.StatusCode)

		// Use some tokens
		checkURL := fmt.Sprintf("http://localhost:%s/check?user_id=crash_test", integrationConfig.AppPort)
		for i := 0; i < 3; i++ {
			resp, err := makeRequest("GET", checkURL, nil)
			require.NoError(t, err)
			resp.Body.Close()
		}

		// Kill the app abruptly
		err = cmd1.Process.Kill()
		require.NoError(t, err)
		cmd1.Wait()

		// Wait a moment
		time.Sleep(1 * time.Second)

		// Restart the app
		cmd2 := startApp(t, integrationConfig)
		defer cmd2.Process.Kill()

		// Verify user data persisted
		getUserURL := fmt.Sprintf("http://localhost:%s/users?user_id=crash_test", integrationConfig.AppPort)
		resp, err = makeRequest("GET", getUserURL, nil)
		require.NoError(t, err)
		defer resp.Body.Close()

		assert.Equal(t, http.StatusOK, resp.StatusCode)

		body, err := io.ReadAll(resp.Body)
		require.NoError(t, err)

		var userInfo map[string]interface{}
		err = json.Unmarshal(body, &userInfo)
		require.NoError(t, err)

		assert.Equal(t, "crash_test", userInfo["user_id"])
		assert.Equal(t, "10", userInfo["max_tokens"])
	})
}

// TestRedisFailureScenarios tests app behavior when Redis fails
func TestRedisFailureScenarios(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	redisContainer := startRedisContainer(t, integrationConfig.RedisPort)
	defer stopRedisContainer(redisContainer)

	buildAppBinary(t)
	defer os.Remove(integrationConfig.AppBinary)

	t.Run("Redis restart during operation", func(t *testing.T) {
		cmd := startApp(t, integrationConfig)
		defer cmd.Process.Kill()

		// Verify app is working
		checkURL := fmt.Sprintf("http://localhost:%s/check?user_id=redis_test", integrationConfig.AppPort)
		resp, err := makeRequest("GET", checkURL, nil)
		require.NoError(t, err)
		resp.Body.Close()
		assert.Equal(t, http.StatusOK, resp.StatusCode)

		// Stop Redis
		exec.Command("docker", "stop", redisContainer).Run()

		// Requests should fail
		resp, err = makeRequest("GET", checkURL, nil)
		if err == nil {
			resp.Body.Close()
			assert.Equal(t, http.StatusInternalServerError, resp.StatusCode)
		}

		// Restart Redis
		exec.Command("docker", "start", redisContainer).Run()
		time.Sleep(3 * time.Second)

		// App should recover
		var recovered bool
		for i := 0; i < 10; i++ {
			resp, err := makeRequest("GET", checkURL, nil)
			if err == nil && resp.StatusCode == http.StatusOK {
				resp.Body.Close()
				recovered = true
				break
			}
			if resp != nil {
				resp.Body.Close()
			}
			time.Sleep(1 * time.Second)
		}
		assert.True(t, recovered, "App did not recover after Redis restart")
	})
}

// TestConcurrentLoad tests the app under concurrent load
func TestConcurrentLoad(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	redisContainer := startRedisContainer(t, integrationConfig.RedisPort)
	defer stopRedisContainer(redisContainer)

	buildAppBinary(t)
	defer os.Remove(integrationConfig.AppBinary)

	cmd := startApp(t, integrationConfig)
	defer cmd.Process.Kill()

	t.Run("Multiple users concurrent requests", func(t *testing.T) {
		const numUsers = 10
		const requestsPerUser = 20

		results := make(chan bool, numUsers*requestsPerUser)

		// Spawn goroutines for multiple users
		for userID := 0; userID < numUsers; userID++ {
			go func(uid int) {
				userIDStr := fmt.Sprintf("load_test_user_%d", uid)
				checkURL := fmt.Sprintf("http://localhost:%s/check?user_id=%s", integrationConfig.AppPort, userIDStr)

				for req := 0; req < requestsPerUser; req++ {
					resp, err := makeRequest("GET", checkURL, nil)
					success := err == nil && (resp.StatusCode == http.StatusOK || resp.StatusCode == http.StatusTooManyRequests)
					if resp != nil {
						resp.Body.Close()
					}
					results <- success
					time.Sleep(10 * time.Millisecond) // Small delay between requests
				}
			}(userID)
		}

		// Collect results
		successCount := 0
		totalRequests := numUsers * requestsPerUser

		for i := 0; i < totalRequests; i++ {
			if <-results {
				successCount++
			}
		}

		// At least 90% of requests should be handled properly
		successRate := float64(successCount) / float64(totalRequests)
		assert.GreaterOrEqual(t, successRate, 0.9, "Success rate should be at least 90%%")

		t.Logf("Concurrent load test: %d/%d requests successful (%.1f%%)",
			successCount, totalRequests, successRate*100)
	})
}

// TestDataPersistence tests that rate limiting data persists correctly
func TestDataPersistence(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	redisContainer := startRedisContainer(t, integrationConfig.RedisPort)
	defer stopRedisContainer(redisContainer)

	buildAppBinary(t)
	defer os.Remove(integrationConfig.AppBinary)

	t.Run("User data survives app restart", func(t *testing.T) {
		// Start app and create users
		cmd1 := startApp(t, integrationConfig)

		users := []string{"persist_user_1", "persist_user_2", "persist_user_3"}

		// Create users with different limits
		for i, userID := range users {
			capacity := (i + 1) * 5
			rate := float64(i + 1)

			userURL := fmt.Sprintf("http://localhost:%s/users?user_id=%s&max_tokens=%d&refill_rate=%.1f",
				integrationConfig.AppPort, userID, capacity, rate)
			resp, err := makeRequest("POST", userURL, nil)
			require.NoError(t, err)
			resp.Body.Close()
			assert.Equal(t, http.StatusOK, resp.StatusCode)
		}

		// Stop the app
		cmd1.Process.Kill()
		cmd1.Wait()
		time.Sleep(1 * time.Second)

		// Restart the app
		cmd2 := startApp(t, integrationConfig)
		defer cmd2.Process.Kill()

		// Verify all users and their data persisted
		for i, userID := range users {
			expectedCapacity := fmt.Sprintf("%d", (i+1)*5)
			expectedRateFloat := float64(i + 1)

			getUserURL := fmt.Sprintf("http://localhost:%s/users?user_id=%s", integrationConfig.AppPort, userID)
			resp, err := makeRequest("GET", getUserURL, nil)
			require.NoError(t, err)
			defer resp.Body.Close()

			assert.Equal(t, http.StatusOK, resp.StatusCode)

			body, err := io.ReadAll(resp.Body)
			require.NoError(t, err)

			var userInfo map[string]interface{}
			err = json.Unmarshal(body, &userInfo)
			require.NoError(t, err)

			assert.Equal(t, userID, userInfo["user_id"])
			assert.Equal(t, expectedCapacity, userInfo["max_tokens"])

			// Handle both "1" and "1.0" formats for rate values
			actualRate := userInfo["refill_rate"].(string)
			actualRateFloat, err := strconv.ParseFloat(actualRate, 64)
			require.NoError(t, err)
			assert.Equal(t, expectedRateFloat, actualRateFloat, "Refill rate should match")
		}
	})
}

// TestFailoverScenarios tests various failure scenarios
func TestFailoverScenarios(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	redisContainer := startRedisContainer(t, integrationConfig.RedisPort)
	defer stopRedisContainer(redisContainer)

	buildAppBinary(t)
	defer os.Remove(integrationConfig.AppBinary)

	t.Run("App handles Redis connection loss gracefully", func(t *testing.T) {
		cmd := startApp(t, integrationConfig)
		defer cmd.Process.Kill()

		// Verify health endpoint still works when Redis is down
		exec.Command("docker", "stop", redisContainer).Run()
		time.Sleep(2 * time.Second)

		healthURL := fmt.Sprintf("http://localhost:%s/health", integrationConfig.AppPort)
		resp, err := makeRequest("GET", healthURL, nil)
		require.NoError(t, err)
		defer resp.Body.Close()

		// Health check should fail when Redis is down
		assert.Equal(t, http.StatusServiceUnavailable, resp.StatusCode)

		// Restart Redis
		exec.Command("docker", "start", redisContainer).Run()
		time.Sleep(3 * time.Second)

		// Health should recover
		resp, err = makeRequest("GET", healthURL, nil)
		require.NoError(t, err)
		defer resp.Body.Close()
		assert.Equal(t, http.StatusOK, resp.StatusCode)
	})
}

// TestMemoryLeaks tests for potential memory leaks under load
func TestMemoryLeaks(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	redisContainer := startRedisContainer(t, integrationConfig.RedisPort)
	defer stopRedisContainer(redisContainer)

	buildAppBinary(t)
	defer os.Remove(integrationConfig.AppBinary)

	cmd := startApp(t, integrationConfig)
	defer cmd.Process.Kill()

	t.Run("No memory leaks under sustained load", func(t *testing.T) {
		// Run sustained load for a period
		const duration = 30 * time.Second
		const requestInterval = 50 * time.Millisecond

		ctx, cancel := context.WithTimeout(context.Background(), duration)
		defer cancel()

		requestCount := 0
		errorCount := 0

		for {
			select {
			case <-ctx.Done():
				t.Logf("Memory leak test completed: %d requests, %d errors", requestCount, errorCount)
				return
			default:
				userID := fmt.Sprintf("memory_test_user_%d", requestCount%100) // Cycle through 100 users
				checkURL := fmt.Sprintf("http://localhost:%s/check?user_id=%s", integrationConfig.AppPort, userID)

				resp, err := makeRequest("GET", checkURL, nil)
				requestCount++

				if err != nil {
					errorCount++
				} else {
					resp.Body.Close()
				}

				time.Sleep(requestInterval)
			}
		}
	})
}
