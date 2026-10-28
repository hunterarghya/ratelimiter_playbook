-- acquire_lease.lua
-- Atomic lease acquisition for Concurrency Rate Limiter using Redis ZSET.
--
-- KEYS[1]: ZSET key: rl:{identity}:{rule_name}:leases
-- ARGV[1]: limit (max concurrent active leases, int)
-- ARGV[2]: lease_id (unique string identifier for this lease)
-- ARGV[3]: lease_ttl_ms (lease validity period in milliseconds)
-- ARGV[4]: now_ms (optional caller timestamp in ms, 0 = use Redis TIME)

local key = KEYS[1]
local limit = tonumber(ARGV[1])
local lease_id = ARGV[2]
local lease_ttl_ms = tonumber(ARGV[3])
local client_now_ms = tonumber(ARGV[4]) or 0

local now_ms
if client_now_ms > 0 then
    now_ms = client_now_ms
else
    local redis_time = redis.call('TIME')
    -- redis_time[1] is unix seconds, redis_time[2] is microseconds
    now_ms = (tonumber(redis_time[1]) * 1000) + math.floor(tonumber(redis_time[2]) / 1000)
end

-- 1. Clean expired leases (reclaim slots abandoned by dead/crashed workers)
redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms)

-- 2. Count current active leases
local active = redis.call('ZCARD', key)

-- 3. Check capacity
if active < limit then
    -- Capacity available: assign lease with expiration score
    local expiry_ms = now_ms + lease_ttl_ms
    redis.call('ZADD', key, expiry_ms, lease_id)

    -- Auto-expire the entire key if idle
    local ttl_sec = math.max(60, math.ceil(lease_ttl_ms / 1000.0) * 2)
    redis.call('EXPIRE', key, ttl_sec)

    local remaining = limit - (active + 1)
    return {
        1,              -- allowed
        remaining,      -- remaining concurrency capacity
        0,              -- retry_after_seconds
        0,              -- reset_seconds
        limit           -- limit
    }
else
    -- Capacity full: find the earliest expiring lease to estimate wait time
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after_sec = 1
    if oldest and #oldest >= 2 then
        local earliest_exp = tonumber(oldest[2])
        local diff_ms = earliest_exp - now_ms
        if diff_ms > 0 then
            retry_after_sec = math.ceil(diff_ms / 1000.0)
        end
    end

    return {
        0,                  -- denied
        0,                  -- remaining
        retry_after_sec,    -- retry_after_seconds
        retry_after_sec,    -- reset_seconds
        limit               -- limit
    }
end
