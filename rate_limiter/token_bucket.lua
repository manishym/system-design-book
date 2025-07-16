-- token_bucket.lua
-- KEYS[1]: Redis key (e.g., user ID)
-- ARGV[1]: max tokens
-- ARGV[2]: refill rate (tokens per second)
-- ARGV[3]: tokens requested (usually 1)
-- ARGV[4]: current timestamp (in seconds)

local key = KEYS[1]
local max_tokens = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local requested = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local bucket = redis.call("HMGET", key, "tokens", "last")
local tokens = tonumber(bucket[1])
local last = tonumber(bucket[2])

if tokens == nil then
  tokens = max_tokens
  last = now
end

local delta = math.max(0, now - last)
tokens = math.min(max_tokens, tokens + delta * refill_rate)

local allowed = tokens >= requested
if allowed then
  tokens = tokens - requested
  redis.call("HMSET", key, "tokens", tokens, "last", now)
  redis.call("EXPIRE", key, 60)
end

return allowed
