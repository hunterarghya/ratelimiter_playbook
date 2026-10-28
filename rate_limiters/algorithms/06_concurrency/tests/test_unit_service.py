"""Unit tests for RateLimiterService using an in-memory FakeRepository for concurrency leases."""

import math

import pytest
from app.schemas.rule import Rule
from app.services.rate_limiter_service import RateLimiterService


class FakeRepository:
    """In-memory simulation of the concurrency lease ZSET in Redis."""

    def __init__(self) -> None:
        self.leases: dict[str, dict[str, int]] = {}
        self.simulated_time_ms: int = 1_000_000

    async def acquire_lease(
        self,
        identity: str,
        rule_name: str,
        limit: int,
        lease_id: str,
        lease_ttl_ms: int,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int]:
        ts = now_ms if now_ms > 0 else self.simulated_time_ms
        key = f"rl:{{{identity}}}:{rule_name}:leases"

        if key not in self.leases:
            self.leases[key] = {}

        # 1. Clean expired leases (score <= ts)
        self.leases[key] = {
            lid: exp for lid, exp in self.leases[key].items() if exp > ts
        }

        # 2. Count active
        active = len(self.leases[key])

        # 3. Check limit
        if active < limit:
            exp_ms = ts + lease_ttl_ms
            self.leases[key][lease_id] = exp_ms
            remaining = limit - (active + 1)
            return 1, remaining, 0, 0, limit
        else:
            # Denied requests consume nothing
            sorted_expiries = sorted(self.leases[key].values())
            earliest_exp = sorted_expiries[0] if sorted_expiries else ts
            diff_ms = max(0, earliest_exp - ts)
            retry_after_sec = math.ceil(diff_ms / 1000.0)
            return 0, 0, retry_after_sec, retry_after_sec, limit

    async def release_lease(
        self,
        identity: str,
        rule_name: str,
        lease_id: str,
    ) -> bool:
        key = f"rl:{{{identity}}}:{rule_name}:leases"
        if key in self.leases and lease_id in self.leases[key]:
            del self.leases[key][lease_id]
            return True
        return False


@pytest.mark.asyncio
async def test_service_acquires_within_limit() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="uploads", limit=2, lease_ttl_seconds=30)

    # Acquire 2 slots
    d1 = await service.acquire("alice", rule)
    assert d1.allowed is True
    assert d1.remaining == 1
    assert d1.lease_id is not None

    d2 = await service.acquire("alice", rule)
    assert d2.allowed is True
    assert d2.remaining == 0
    assert d2.lease_id is not None

    # 3rd acquire is full
    d3 = await service.acquire("alice", rule)
    assert d3.allowed is False
    assert d3.remaining == 0
    assert d3.lease_id is None
    assert d3.retry_after >= 1


@pytest.mark.asyncio
async def test_service_release_frees_capacity() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="uploads", limit=2, lease_ttl_seconds=30)

    d1 = await service.acquire("alice", rule)
    d2 = await service.acquire("alice", rule)
    assert d1.lease_id is not None
    assert d2.allowed is True

    # Release first lease
    released = await service.release("alice", rule, d1.lease_id)
    assert released is True

    # Now a new lease can be acquired
    d3 = await service.acquire("alice", rule)
    assert d3.allowed is True
    assert d3.remaining == 0


@pytest.mark.asyncio
async def test_service_expired_lease_is_automatically_reclaimed() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="uploads", limit=1, lease_ttl_seconds=10)

    # Acquire only slot
    d1 = await service.acquire("alice", rule)
    assert d1.allowed is True

    # Advance time past lease TTL (10s = 10,000ms) without calling release (worker crashed)
    repo.simulated_time_ms += 11_000

    # Next acquire should reclaim the expired slot automatically
    d2 = await service.acquire("alice", rule)
    assert d2.allowed is True
    assert d2.remaining == 0


@pytest.mark.asyncio
async def test_release_is_idempotent() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="uploads", limit=2, lease_ttl_seconds=30)

    # Release non-existent lease
    released = await service.release("alice", rule, "ghost-lease")
    assert released is False

    # Acquire and double release
    d1 = await service.acquire("alice", rule)
    assert d1.lease_id is not None
    assert await service.release("alice", rule, d1.lease_id) is True
    assert await service.release("alice", rule, d1.lease_id) is False


@pytest.mark.asyncio
async def test_denied_requests_do_not_occupy_slots() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="uploads", limit=1, lease_ttl_seconds=30)

    d1 = await service.acquire("alice", rule)
    assert d1.allowed is True

    # 5 denied requests
    for _ in range(5):
        d = await service.acquire("alice", rule)
        assert d.allowed is False

    key = "rl:{alice}:uploads:leases"
    assert len(repo.leases[key]) == 1
