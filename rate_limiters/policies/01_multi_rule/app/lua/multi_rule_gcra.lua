-- multi_rule_gcra.lua
-- Atomic all-or-nothing evaluation of multiple GCRA rules.
--
-- KEYS[1..N]: rl:{identity}:{rule_name}:gcra (all keys share {identity} hash tag)
-- ARGV[1]: cost
-- ARGV[2]: now_ms (0 = use Redis TIME)
-- For each i in 1..N:
--   ARGV[3 + (i-1)*4]: T_ms
--   ARGV[4 + (i-1)*4]: tau_ms
--   ARGV[5 + (i-1)*4]: burst
--   ARGV[6 + (i-1)*4]: rule_name

local num_rules = #KEYS
local cost = tonumber(ARGV[1]) or 1
local client_now_ms = tonumber(ARGV[2]) or 0

local now_ms
if client_now_ms > 0 then
    now_ms = client_now_ms
else
    local redis_time = redis.call('TIME')
    now_ms = (tonumber(redis_time[1]) * 1000) + math.floor(tonumber(redis_time[2]) / 1000)
end

-- Phase 1: Dry-run evaluation across all rules
local any_denied = false
local max_retry_after_ms = 0
local violated_rule = ""
local rule_evals = {}
local min_remaining = 999999999
local max_reset_sec = 0
local min_limit = 999999999

for i = 1, num_rules do
    local key = KEYS[i]
    local base_arg = 3 + (i - 1) * 4
    local T_ms = tonumber(ARGV[base_arg])
    local tau_ms = tonumber(ARGV[base_arg + 1])
    local burst = tonumber(ARGV[base_arg + 2])
    local rule_name = ARGV[base_arg + 3]

    if burst < min_limit then
        min_limit = burst
    end

    local tat_str = redis.call('GET', key)
    local tat = tat_str and tonumber(tat_str) or 0
    local base_tat = math.max(tat, now_ms)
    local new_tat = base_tat + (T_ms * cost)
    local earliest_allowed = new_tat - tau_ms

    if now_ms < earliest_allowed then
        any_denied = true
        local deficit_ms = earliest_allowed - now_ms
        if deficit_ms > max_retry_after_ms then
            max_retry_after_ms = deficit_ms
            violated_rule = rule_name
        end
    else
        local avail_time = math.max(0, (now_ms + tau_ms) - new_tat)
        local rem = math.min(burst, math.floor(avail_time / T_ms))
        if rem < min_remaining then
            min_remaining = rem
        end
        local reset_ms = math.max(0, new_tat - now_ms)
        local reset_sec = math.ceil(reset_ms / 1000.0)
        if reset_sec > max_reset_sec then
            max_reset_sec = reset_sec
        end
    end

    rule_evals[i] = {
        key = key,
        new_tat = new_tat,
        tau_ms = tau_ms,
        T_ms = T_ms
    }
end

-- Phase 2: All-or-Nothing Commit or Abort
if any_denied then
    -- ABORT: CHARGE NOTHING! No Redis keys are updated.
    local retry_after_sec = math.ceil(max_retry_after_ms / 1000.0)
    return {
        0,                  -- allowed
        0,                  -- remaining
        retry_after_sec,    -- retry_after_seconds
        retry_after_sec,    -- reset_seconds
        min_limit,          -- limit
        violated_rule       -- violated_rule
    }
else
    -- COMMIT: Update all rules atomically
    for i = 1, num_rules do
        local r = rule_evals[i]
        redis.call('SET', r.key, tostring(r.new_tat))
        local reset_ms = math.max(0, r.new_tat - now_ms)
        local ttl_sec = math.max(60, math.ceil(reset_ms / 1000.0) + 60)
        redis.call('EXPIRE', r.key, ttl_sec)
    end

    if min_remaining == 999999999 then
        min_remaining = 0
    end

    return {
        1,                  -- allowed
        min_remaining,      -- remaining
        0,                  -- retry_after_seconds
        max_reset_sec,      -- reset_seconds
        min_limit,          -- limit
        ""                  -- no violated rule
    }
end
