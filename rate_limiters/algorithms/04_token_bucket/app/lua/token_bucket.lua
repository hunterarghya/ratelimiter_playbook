-- token_bucket.lua
-- Atomic Token Bucket rate limiter using Redis HASH.
--
-- KEYS[1]: Hash key: rl:{identity}:{rule_name}:tb
-- ARGV[1]: capacity (max tokens bucket can hold, float/int)
-- ARGV[2]: refill_rate_per_sec (tokens added per second, float)
-- ARGV[3]: cost (tokens required for this request, int >= 1)
-- ARGV[4]: now_ms (optional caller timestamp in ms, 0 = use Redis TIME)

local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate_per_sec = tonumber(ARGV[2])
local cost = tonumber(ARGV[3]) or 1
local client_now_ms = tonumber(ARGV[4]) or 0

local now_ms
if client_now_ms > 0 then
    now_ms = client_now_ms
else
    local redis_time = redis.call('TIME')
    -- redis_time[1] is unix seconds, redis_time[2] is microseconds
    now_ms = (tonumber(redis_time[1]) * 1000) + math.floor(tonumber(redis_time[2]) / 1000)
end

-- 1. Read existing bucket state
local data = redis.call('HMGET', key, 'tokens', 'last_ts')
local current_tokens = tonumber(data[1])
local last_ts = tonumber(data[2])

if not current_tokens or not last_ts then
    -- Bucket has not been initialized yet: starts completely full
    current_tokens = capacity
    last_ts = now_ms
else
    -- 2. Lazy refill: add tokens proportionally to elapsed wall-clock time
    local elapsed_ms = math.max(0, now_ms - last_ts)
    local refilled = (elapsed_ms / 1000.0) * refill_rate_per_sec
    current_tokens = math.min(capacity, current_tokens + refilled)
    last_ts = now_ms
end

-- 3. Check capacity and consume
local allowed = 0
local retry_after_sec = 0

if current_tokens >= cost then
    allowed = 1
    current_tokens = current_tokens - cost
    -- Save decremented token balance and timestamp
    redis.call('HSET', key, 'tokens', tostring(current_tokens), 'last_ts', tostring(now_ms))
else
    allowed = 0
    -- Denied requests consume NOTHING (tokens balance is not deducted).
    -- Save refilled tokens and advance last_ts so past time is not refilled repeatedly.
    redis.call('HSET', key, 'tokens', tostring(current_tokens), 'last_ts', tostring(now_ms))
    local deficit = cost - current_tokens
    retry_after_sec = deficit / refill_rate_per_sec
end

-- 4. TTL: time to fill from 0 to full capacity, doubled as a safety margin
local fill_time_sec = math.ceil(capacity / refill_rate_per_sec)
local ttl_sec = math.max(60, fill_time_sec * 2)
redis.call('EXPIRE', key, ttl_sec)

-- 5. Calculate reset: seconds until bucket reaches full capacity
local missing_tokens = math.max(0, capacity - current_tokens)
local reset_sec = missing_tokens / refill_rate_per_sec

-- Return values:
-- [1]: allowed (1 or 0)
-- [2]: remaining (floor of current_tokens)
-- [3]: retry_after_seconds (math.ceil of retry_after_sec)
-- [4]: reset_seconds (math.ceil of reset_sec)
-- [5]: capacity (integer capacity)
return {
    allowed,
    math.floor(current_tokens),
    math.ceil(retry_after_sec),
    math.ceil(reset_sec),
    math.floor(capacity)
}
