"""Fixtures for HTTP contract tests."""

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--target-url",
        action="store",
        default=os.environ.get("TARGET_URL", "http://localhost:8101"),
        help="Target base URL of the rate limiter service under test",
    )


@pytest.fixture
def target_url(request: pytest.FixtureRequest) -> str:
    url = request.config.getoption("--target-url")
    return str(url).rstrip("/")
