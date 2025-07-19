-- token_bucket.lua
-- KEYS[1]: Redis key for user bucket (e.g., "ratelimit:token:userID")
-- ARGV[1]: default max tokens (used for new users)
-- ARGV[2]: default refill rate (tokens per second, used for new users)
-- ARGV[3]: tokens requested (usually 1)
-- ARGV[4]: current timestamp (in seconds)
-- ARGV[5]: user ID

local key = KEYS[1]
local default_max_tokens = tonumber(ARGV[1])
local default_refill_rate = tonumber(ARGV[2])
local requested = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local user_id = ARGV[5]

-- Validate input parameters
if not default_max_tokens or not default_refill_rate or not requested or not now or not user_id then
  return 0
end

-- User configuration key
local user_config_key = "ratelimit:users:" .. user_id
local users_set_key = "ratelimit:users"

-- Check if user exists and get their configuration
local user_exists = redis.call("SISMEMBER", users_set_key, user_id)
local max_tokens, refill_rate

if user_exists == 1 then
  -- User exists, get their specific limits
  local user_config = redis.call("HMGET", user_config_key, "max_tokens", "refill_rate")
  max_tokens = tonumber(user_config[1]) or default_max_tokens
  refill_rate = tonumber(user_config[2]) or default_refill_rate
else
  -- New user, initialize with default limits
  max_tokens = default_max_tokens
  refill_rate = default_refill_rate
  
  -- Add user to users set
  redis.call("SADD", users_set_key, user_id)
  
  -- Store user configuration
  redis.call("HMSET", user_config_key, 
    "max_tokens", max_tokens,
    "refill_rate", refill_rate,
    "created_at", now)
  
  -- Set expiration for user config (24 hours)
  redis.call("EXPIRE", user_config_key, 86400)
end

-- Get current bucket state
local bucket = redis.call("HMGET", key, "tokens", "last")
local tokens = tonumber(bucket[1])
local last = tonumber(bucket[2])

-- Initialize bucket if it doesn't exist or if it's a new user without a bucket
if tokens == nil then
  tokens = max_tokens
  last = now
end

-- Calculate token refill based on time elapsed
local delta = math.max(0, now - last)
tokens = math.min(max_tokens, tokens + delta * refill_rate)

-- Check if request can be allowed
local allowed = tokens >= requested

if allowed then
  tokens = tokens - requested
  redis.call("HMSET", key, "tokens", tokens, "last", now)
  redis.call("EXPIRE", key, 3600)  -- Expire bucket after 1 hour of inactivity
  return 1  -- Request allowed
else
  -- Update the last seen time even for denied requests
  redis.call("HMSET", key, "tokens", tokens, "last", now)
  redis.call("EXPIRE", key, 3600)
  return 0  -- Request denied
end
