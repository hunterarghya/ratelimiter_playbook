-- gcra.lua
-- Generic Cell Rate Algorithm (GCRA) using Redis string key.
--
-- KEYS[1]: String key: rl:{identity}:{rule_name}:gcra
-- ARGV[1]: T_ms (emission interval per request in milliseconds: (period * 1000) / limit)
-- ARGV[2]: tau_ms (burst tolerance in milliseconds: T_ms * burst)
-- ARGV[3]: cost (cost multiplier for this request, int >= 1)
-- ARGV[4]: burst (integer burst capacity)
-- ARGV[5]: now_ms (optional caller timestamp in ms, 0 = use Redis TIME)

local key = KEYS[1]
local T_ms = tonumber(ARGV[1])
local tau_ms = tonumber(ARGV[2])
local cost = tonumber(ARGV[3]) or 1
local burst = tonumber(ARGV[4])
local client_now_ms = tonumber(ARGV[5]) or 0

local now_ms
if client_now_ms > 0 then
    now_ms = client_now_ms
else
    local redis_time = redis.call('TIME')
    -- redis_time[1] is unix seconds, redis_time[2] is microseconds
    now_ms = (tonumber(redis_time[1]) * 1000) + math.floor(tonumber(redis_time[2]) / 1000)
end

-- 1. Read existing TAT (Theoretical Arrival Time)
local tat_str = redis.call('GET', key)
local tat = tat_str and tonumber(tat_str) or 0

-- 2. Calculate projected new TAT
local base_tat = math.max(tat, now_ms)
local increment_ms = T_ms * cost
local new_tat = base_tat + increment_ms
local earliest_allowed = new_tat - tau_ms

local allowed = 0
local retry_after_sec = 0

-- 3. Evaluate admission decision
if now_ms < earliest_allowed then
    -- DENIED: TAT has run too far ahead of the clock
    -- Denied requests consume nothing: TAT is NOT updated
    allowed = 0
    local deficit_ms = earliest_allowed - now_ms
    retry_after_sec = math.ceil(deficit_ms / 1000.0)
else
    -- ALLOWED: advance TAT to new_tat
    allowed = 1
    tat = new_tat
    redis.call('SET', key, tostring(tat))
    retry_after_sec = 0
end

-- 4. TTL: set key to expire once TAT returns to the clock plus buffer
local reset_ms = math.max(0, tat - now_ms)
local ttl_sec = math.max(60, math.ceil(reset_ms / 1000.0) + 60)
redis.call('EXPIRE', key, ttl_sec)

-- 5. Calculate remaining capacity and reset seconds
local available_time = math.max(0, (now_ms + tau_ms) - tat)
local remaining = math.floor(available_time / T_ms)
if remaining > burst then
    remaining = burst
end
local reset_sec = math.ceil(reset_ms / 1000.0)

-- Return:
-- [1]: allowed (1 or 0)
-- [2]: remaining (integer count)
-- [3]: retry_after_seconds (integer)
-- [4]: reset_seconds (integer)
-- [5]: burst (integer limit)
return {
    allowed,
    remaining,
    retry_after_sec,
    reset_sec,
    burst
}
