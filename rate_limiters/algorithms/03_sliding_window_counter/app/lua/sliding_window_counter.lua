-- sliding_window_counter.lua
-- Approximate sliding-window rate limit using two fixed-window counters.
--
-- The idea: keep a counter for the *previous* window and the *current* window.
-- Estimate how many requests fell in the last "window" seconds by blending:
--
--   estimated = prev_count × (1 − elapsed_fraction) + curr_count
--
-- where elapsed_fraction = (now_ms − current_window_start) / window_ms.
--
-- This is O(1) memory (two small keys) and close to exact for typical traffic.
--
-- KEYS[1]: current window counter key,  e.g. rl:{user:alice}:api:swc:<window_num>
-- KEYS[2]: previous window counter key, e.g. rl:{user:alice}:api:swc:<window_num-1>
-- ARGV[1]: limit
-- ARGV[2]: window_ms (window duration in milliseconds)
-- ARGV[3]: now_ms (optional client timestamp in ms; if 0, redis TIME is used)
-- ARGV[4]: current_window_start_ms (start of the current fixed window in ms)

local limit      = tonumber(ARGV[1])
local window_ms  = tonumber(ARGV[2])

-- 1. Determine current timestamp in milliseconds
local now_ms = tonumber(ARGV[3])
if not now_ms or now_ms <= 0 then
  local t = redis.call('TIME')
  now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
end

local window_start_ms = tonumber(ARGV[4])

-- 2. Read counters
local prev_count = tonumber(redis.call('GET', KEYS[2]) or '0') or 0
local curr_count = tonumber(redis.call('GET', KEYS[1]) or '0') or 0

-- 3. Compute the weighted estimate
local elapsed_ms = now_ms - window_start_ms
if elapsed_ms < 0 then elapsed_ms = 0 end
local elapsed_fraction = elapsed_ms / window_ms  -- 0.0 to ~1.0
if elapsed_fraction > 1 then elapsed_fraction = 1 end

local weight = 1 - elapsed_fraction
local estimated = math.floor(prev_count * weight + curr_count)

if estimated < limit then
  -- ALLOWED: increment the current window counter
  local new_count = redis.call('INCR', KEYS[1])

  -- Set TTL on the current window key: 2 × window so the key lives through
  -- the next window (it becomes the "previous" window for the next period)
  local ttl_ms = window_ms * 2
  redis.call('PEXPIRE', KEYS[1], ttl_ms)

  -- Also refresh TTL on previous window key if it exists
  local prev_ttl = redis.call('PTTL', KEYS[2])
  if prev_ttl > 0 then
    -- keep it alive for at least the remaining window time
    local remaining_window = window_ms - elapsed_ms
    if remaining_window > 0 and prev_ttl < remaining_window then
      redis.call('PEXPIRE', KEYS[2], remaining_window)
    end
  end

  local new_estimated = math.floor(prev_count * weight + new_count)
  local remaining = limit - new_estimated
  if remaining < 0 then remaining = 0 end

  -- reset = seconds until the current window ends
  local reset_ms = window_ms - elapsed_ms
  if reset_ms < 0 then reset_ms = 0 end
  local reset_s = math.ceil(reset_ms / 1000)

  return {1, remaining, 0, reset_s, estimated, new_estimated}
else
  -- DENIED: do NOT increment (denied requests consume nothing)

  -- retry_after: how long until enough weight shifts to allow one more
  -- We need estimated < limit after more time passes.
  -- As time passes, weight decreases: estimated ≈ prev_count*(1 - t/W) + curr_count
  -- We want prev_count*(1 - t/W) + curr_count < limit
  --   => prev_count*(1 - t/W) < limit - curr_count
  --   => 1 - t/W < (limit - curr_count) / prev_count
  --   => t/W > 1 - (limit - curr_count) / prev_count
  --   => t > W * (1 - (limit - curr_count) / prev_count)
  local retry_after_ms
  if prev_count > 0 and curr_count < limit then
    local needed_fraction = 1 - (limit - curr_count) / prev_count
    if needed_fraction <= 0 then
      retry_after_ms = 0
    else
      retry_after_ms = math.ceil(needed_fraction * window_ms)
    end
    -- Subtract already elapsed time
    retry_after_ms = retry_after_ms - elapsed_ms
    if retry_after_ms < 0 then retry_after_ms = 0 end
  else
    -- prev_count is 0, all requests are in current window: wait for window end
    retry_after_ms = window_ms - elapsed_ms
  end
  if retry_after_ms < 0 then retry_after_ms = 0 end

  local retry_after_s = math.ceil(retry_after_ms / 1000)
  if retry_after_s < 1 then retry_after_s = 1 end

  local reset_ms = window_ms - elapsed_ms
  if reset_ms < 0 then reset_ms = 0 end
  local reset_s = math.ceil(reset_ms / 1000)

  return {0, 0, retry_after_s, reset_s, estimated, estimated}
end
