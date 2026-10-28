-- sliding_window_log.lua
-- Implements exact sliding window log rate limiting using a Redis ZSET.
--
-- KEYS[1]: Redis ZSET key, e.g. rl:{user:alice}:login:log
-- ARGV[1]: limit (max allowed entries in sliding window)
-- ARGV[2]: window_ms (window duration in milliseconds)
-- ARGV[3]: now_ms (optional client timestamp in ms; if 0, redis.call('TIME') is used)

local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])

-- 1. Determine current timestamp in milliseconds
local now_ms = tonumber(ARGV[3])
if not now_ms or now_ms <= 0 then
  local time_parts = redis.call('TIME')
  now_ms = tonumber(time_parts[1]) * 1000 + math.floor(tonumber(time_parts[2]) / 1000)
end

local clear_before = now_ms - window_ms

-- 2. Drop all entries outside the sliding window
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', clear_before)

-- 3. Count remaining entries
local current_count = redis.call('ZCARD', KEYS[1])

if current_count < limit then
  -- ALLOWED: add entry to the log with score = now_ms
  -- Unique member: <now_ms>:<unique_counter>
  local member = tostring(now_ms) .. ':' .. tostring(current_count + 1)
  redis.call('ZADD', KEYS[1], now_ms, member)
  redis.call('PEXPIRE', KEYS[1], window_ms)

  local remaining = limit - (current_count + 1)
  local reset_seconds = math.ceil(window_ms / 1000)
  return {1, remaining, 0, reset_seconds}
else
  -- DENIED: do NOT add to ZSET (denied requests must not pollute the diary)
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  local retry_after_ms = 0
  if #oldest > 0 then
    local oldest_ts = tonumber(oldest[2])
    retry_after_ms = (oldest_ts + window_ms) - now_ms
    if retry_after_ms < 0 then retry_after_ms = 0 end
  else
    retry_after_ms = window_ms
  end

  local retry_after_s = math.ceil(retry_after_ms / 1000)
  if retry_after_s < 1 then retry_after_s = 1 end

  -- Keep key TTL refreshed
  redis.call('PEXPIRE', KEYS[1], window_ms)
  return {0, 0, retry_after_s, retry_after_s}
end
