-- leaky_bucket.lua
-- Leaky bucket rate limiting algorithm with multi-user support
-- KEYS[1]: Redis key for user bucket (e.g., "ratelimit:leaky:userID")
-- ARGV[1]: default bucket capacity (max requests that can be queued, used for new users)
-- ARGV[2]: default leak rate (requests per second that can be processed, used for new users)
-- ARGV[3]: requests to add (usually 1)
-- ARGV[4]: current timestamp (in seconds)
-- ARGV[5]: user ID

local key = KEYS[1]
local default_capacity = tonumber(ARGV[1])
local default_leak_rate = tonumber(ARGV[2])
local requests_to_add = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local user_id = ARGV[5]

-- Validate input parameters
if not default_capacity or not default_leak_rate or not requests_to_add or not now or not user_id then
  return 0
end

-- User configuration key
local user_config_key = "ratelimit:users:" .. user_id
local users_set_key = "ratelimit:users"

-- Check if user exists and get their configuration
local user_exists = redis.call("SISMEMBER", users_set_key, user_id)
local capacity, leak_rate

if user_exists == 1 then
  -- User exists, get their specific limits
  local user_config = redis.call("HMGET", user_config_key, "capacity", "leak_rate")
  capacity = tonumber(user_config[1]) or default_capacity
  leak_rate = tonumber(user_config[2]) or default_leak_rate
else
  -- New user, initialize with default limits
  capacity = default_capacity
  leak_rate = default_leak_rate
  
  -- Add user to users set
  redis.call("SADD", users_set_key, user_id)
  
  -- Store user configuration
  redis.call("HMSET", user_config_key, 
    "capacity", capacity,
    "leak_rate", leak_rate,
    "created_at", now)
  
  -- Set expiration for user config (24 hours)
  redis.call("EXPIRE", user_config_key, 86400)
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
  redis.call("EXPIRE", key, 3600)  -- Expire bucket after 1 hour of inactivity
  
  return 1  -- Request allowed
else
  -- Update last_leak time even if request is rejected
  redis.call("HMSET", key, "volume", current_volume, "last_leak", now)
  redis.call("EXPIRE", key, 3600)
  
  return 0  -- Request denied (bucket would overflow)
end
