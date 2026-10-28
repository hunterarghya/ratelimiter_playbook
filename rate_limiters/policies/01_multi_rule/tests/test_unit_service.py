"""Unit tests for RateLimiterService using FakeRepository for multi-rule policy."""

import math

import pytest
from app.schemas.rule import Rule
from app.services.rate_limiter_service import RateLimiterService


class FakeRepository:
    """In-memory simulation of the multi-rule GCRA Lua script."""

    def __init__(self) -> None:
        self.tats: dict[str, int] = {}
        self.simulated_time_ms: int = 1_000_000

    async def evaluate_multi_rule(
        self,
        identity: str,
        rules: list[Rule],
        cost: int = 1,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int, str]:
        ts = now_ms if now_ms > 0 else self.simulated_time_ms

        any_denied = False
        max_retry_after_ms = 0
        violated_rule = ""
        min_remaining = 999999999
        max_reset_sec = 0
        min_limit = 999999999
        projected_tats: dict[str, int] = {}

        # Phase 1: Dry run
        for r in rules:
            key = f"rl:{{{identity}}}:{r.name}:gcra"
            if r.burst < min_limit:
                min_limit = r.burst

            t_ms = (r.period * 1000.0) / float(r.limit)
            tau_ms = t_ms * float(r.burst)

            current_tat = self.tats.get(key, 0)
            base_tat = max(current_tat, ts)
            new_tat = int(base_tat + (t_ms * cost))
            earliest_allowed = new_tat - tau_ms

            if ts < earliest_allowed:
                any_denied = True
                deficit_ms = int(earliest_allowed - ts)
                if deficit_ms > max_retry_after_ms:
                    max_retry_after_ms = deficit_ms
                    violated_rule = r.name
            else:
                avail_time = max(0.0, (ts + tau_ms) - new_tat)
                rem = min(r.burst, math.floor(avail_time / t_ms))
                if rem < min_remaining:
                    min_remaining = rem
                reset_ms = max(0, new_tat - ts)
                reset_sec = math.ceil(reset_ms / 1000.0)
                if reset_sec > max_reset_sec:
                    max_reset_sec = reset_sec

            projected_tats[key] = new_tat

        # Phase 2: All-or-nothing
        if any_denied:
            # CHARGE NOTHING
            retry_sec = math.ceil(max_retry_after_ms / 1000.0)
            return 0, 0, retry_sec, retry_sec, min_limit, violated_rule
        else:
            # Commit all
            for k, val in projected_tats.items():
                self.tats[k] = val
            rem_res = min_remaining if min_remaining != 999999999 else 0
            return 1, rem_res, 0, max_reset_sec, min_limit, ""


@pytest.mark.asyncio
async def test_service_allows_when_all_rules_pass() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rules = [
        Rule(name="sec", limit=5, period=1, burst=5),
        Rule(name="hour", limit=100, period=3600, burst=100),
    ]

    decision = await service.evaluate("alice", rules)
    assert decision.allowed is True
    assert decision.remaining == 4  # 5-1=4 (min remaining)
    assert decision.violated_rule is None


@pytest.mark.asyncio
async def test_service_denies_and_charges_nothing_when_one_rule_fails() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule_sec = Rule(name="sec", limit=5, period=1, burst=5)
    rule_hour = Rule(name="hour", limit=2, period=3600, burst=2)
    rules = [rule_sec, rule_hour]

    # First 2 requests pass both rules
    d1 = await service.evaluate("alice", rules)
    d2 = await service.evaluate("alice", rules)
    assert d1.allowed is True
    assert d2.allowed is True

    sec_key = "rl:{alice}:sec:gcra"
    hour_key = "rl:{alice}:hour:gcra"
    sec_tat_before = repo.tats[sec_key]
    hour_tat_before = repo.tats[hour_key]

    # 3rd request passes sec rule but FAILS hour rule!
    d3 = await service.evaluate("alice", rules)
    assert d3.allowed is False
    assert d3.violated_rule == "hour"

    # CRITICAL INVARIANT: sec rule was NOT charged! TAT unchanged!
    assert repo.tats[sec_key] == sec_tat_before
    assert repo.tats[hour_key] == hour_tat_before


@pytest.mark.asyncio
async def test_service_reports_longest_violated_rule_and_max_retry_after() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    # Drain both rules
    rule_short = Rule(name="short", limit=1, period=2, burst=1)
    rule_long = Rule(name="long", limit=1, period=3600, burst=1)
    rules = [rule_short, rule_long]

    # First call allowed
    await service.evaluate("alice", rules)

    # Second call fails BOTH rules. Long rule has ~3600s deficit, short has ~2s deficit
    d = await service.evaluate("alice", rules)
    assert d.allowed is False
    assert d.violated_rule == "long"
    assert d.retry_after >= 3500
