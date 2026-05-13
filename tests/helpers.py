"""Test fixtures: deterministic clock and Store factory."""

from __future__ import annotations

from collections.abc import Callable

from mini_redis.store import Store


class FakeClock:
    """Monotonic fake clock for TTL tests (Phase 4)."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


def make_store(clock: Callable[[], float] | None = None) -> Store:
    """Build a Store with optional injected clock."""
    return Store(clock=clock)
