-- leaky_bucket.lua
-- Leaky bucket rate limiting algorithm
-- KEYS[1]: Redis key (e.g., user ID)
-- ARGV[1]: bucket capacity (max requests that can be queued)
-- ARGV[2]: leak rate (requests per second that can be processed)
-- ARGV[3]: requests to add (usually 1)
-- ARGV[4]: current timestamp (in seconds)

local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local leak_rate = tonumber(ARGV[2])
local requests_to_add = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

-- Validate input parameters
if not capacity or not leak_rate or not requests_to_add or not now then
  return 0
end

-- Get current bucket state
local bucket = redis.call("HMGET", key, "volume", "last_leak")
local current_volume = tonumber(bucket[1]) or 0
local last_leak = tonumber(bucket[2]) or now

-- Calculate how much should have leaked since last check
local time_passed = math.max(0, now - last_leak)
local leaked_amount = time_passed * leak_rate

-- Update volume after leaking
current_volume = math.max(0, current_volume - leaked_amount)

-- Check if we can add the new requests
if current_volume + requests_to_add <= capacity then
  -- Add requests to bucket
  current_volume = current_volume + requests_to_add
  
  -- Update bucket state
  redis.call("HMSET", key, "volume", current_volume, "last_leak", now)
  redis.call("EXPIRE", key, 60)
  
  return 1  -- Request allowed
else
  -- Update last_leak time even if request is rejected
  redis.call("HMSET", key, "volume", current_volume, "last_leak", now)
  redis.call("EXPIRE", key, 60)
  
  return 0  -- Request denied (bucket would overflow)
end
