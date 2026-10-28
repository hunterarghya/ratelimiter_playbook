-- refund_gcra.lua
-- Settles / refunds unused cost units into a GCRA string key.
-- Invariant: refund cannot shift TAT earlier than now_ms (cannot exceed full capacity).
--
-- KEYS[1]: String key: rl:{identity}:weighted_gcra
-- ARGV[1]: T_ms (emission interval per cost unit in ms)
-- ARGV[2]: tau_ms (burst tolerance in ms)
-- ARGV[3]: refund_cost (number of cost units to refund)
-- ARGV[4]: burst (integer burst capacity)
-- ARGV[5]: now_ms (optional caller timestamp in ms)

local key = KEYS[1]
local T_ms = tonumber(ARGV[1])
local tau_ms = tonumber(ARGV[2])
local refund_cost = tonumber(ARGV[3]) or 0
local burst = tonumber(ARGV[4])
local client_now_ms = tonumber(ARGV[5]) or 0

local now_ms
if client_now_ms > 0 then
    now_ms = client_now_ms
else
    local redis_time = redis.call('TIME')
    now_ms = (tonumber(redis_time[1]) * 1000) + math.floor(tonumber(redis_time[2]) / 1000)
end

local tat_str = redis.call('GET', key)
local tat = tat_str and tonumber(tat_str) or now_ms

if refund_cost > 0 then
    local refund_ms = T_ms * refund_cost
    -- INVARIANT: Cannot exceed burst capacity!
    -- Full capacity corresponds to TAT <= now_ms.
    -- Refunding can pull TAT backward, but never earlier than now_ms.
    local new_tat = math.max(now_ms, tat - refund_ms)
    tat = new_tat
    redis.call('SET', key, tostring(tat))

    local reset_ms = math.max(0, tat - now_ms)
    local ttl_sec = math.max(60, math.ceil(reset_ms / 1000.0) + 60)
    redis.call('EXPIRE', key, ttl_sec)
end

-- Remaining capacity calculation
local available_time = math.max(0, (now_ms + tau_ms) - tat)
local remaining = math.floor(available_time / T_ms)
if remaining > burst then
    remaining = burst
end

return {
    1,          -- success
    remaining,  -- updated remaining capacity
    tat         -- updated theoretical arrival time
}
