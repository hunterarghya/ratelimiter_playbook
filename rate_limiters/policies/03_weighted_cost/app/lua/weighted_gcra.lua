-- weighted_gcra.lua
-- Weighted GCRA evaluation with permanent rejection for cost > burst.
--
-- KEYS[1]: String key: rl:{identity}:weighted_gcra
-- ARGV[1]: T_ms (emission interval per cost unit in ms: (period * 1000) / limit)
-- ARGV[2]: tau_ms (burst tolerance in ms: T_ms * burst)
-- ARGV[3]: cost (requested cost units, int >= 1)
-- ARGV[4]: burst (integer burst capacity)
-- ARGV[5]: now_ms (optional caller timestamp in ms, 0 = use Redis TIME)

local key = KEYS[1]
local T_ms = tonumber(ARGV[1])
local tau_ms = tonumber(ARGV[2])
local cost = tonumber(ARGV[3]) or 1
local burst = tonumber(ARGV[4])
local client_now_ms = tonumber(ARGV[5]) or 0

-- 1. Permanent rejection check: cost > burst
-- No amount of waiting will EVER permit a request whose cost exceeds burst capacity!
if cost > burst then
    -- Return code -1 signals permanent rejection (HTTP 422 / 400, never retry)
    return {
        -1,     -- allowed: -1 (exceeds_burst)
        0,      -- remaining: 0
        0,      -- retry_after_seconds: 0 (non-retryable)
        0,      -- reset_seconds: 0
        burst   -- limit / burst capacity
    }
end

local now_ms
if client_now_ms > 0 then
    now_ms = client_now_ms
else
    local redis_time = redis.call('TIME')
    now_ms = (tonumber(redis_time[1]) * 1000) + math.floor(tonumber(redis_time[2]) / 1000)
end

-- 2. Read existing TAT
local tat_str = redis.call('GET', key)
local tat = tat_str and tonumber(tat_str) or 0

-- 3. Calculate projected new TAT
local base_tat = math.max(tat, now_ms)
local increment_ms = T_ms * cost
local new_tat = base_tat + increment_ms
local earliest_allowed = new_tat - tau_ms

local allowed = 0
local retry_after_sec = 0

-- 4. Evaluate admission decision
if now_ms < earliest_allowed then
    -- DENIED: TAT has advanced too far ahead of the clock
    allowed = 0
    local deficit_ms = earliest_allowed - now_ms
    retry_after_sec = math.ceil(deficit_ms / 1000.0)
else
    -- ALLOWED: advance TAT
    allowed = 1
    tat = new_tat
    redis.call('SET', key, tostring(tat))
    retry_after_sec = 0
end

-- 5. TTL calculation
local reset_ms = math.max(0, tat - now_ms)
local ttl_sec = math.max(60, math.ceil(reset_ms / 1000.0) + 60)
redis.call('EXPIRE', key, ttl_sec)

-- 6. Calculate remaining capacity in cost units
local available_time = math.max(0, (now_ms + tau_ms) - tat)
local remaining = math.floor(available_time / T_ms)
if remaining > burst then
    remaining = burst
end
local reset_sec = math.ceil(reset_ms / 1000.0)

return {
    allowed,
    remaining,
    retry_after_sec,
    reset_sec,
    burst
}
