"""In-memory key-value store: string commands, LRU wiring, memory accounting."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from mini_redis.hashmap import HashMap
from mini_redis.heap import MinHeap
from mini_redis.linked_list import DoublyLinkedList, Node


def _utf8_len(s: str) -> int:
    """Return byte length of *s* encoded as UTF-8."""
    return len(s.encode("utf-8"))


@dataclass(slots=True)
class Entry:
    """Stored key-value with cached byte size and LRU list node."""

    key: str
    value: str
    entry_bytes: int
    lru_node: Node


@dataclass(slots=True)
class StoreMetrics:
    """Snapshot fields aligned with INFO memory (subject §4.3)."""

    used_memory: int = 0
    maxmemory: int = 0
    evicted_keys: int = 0


class Store:
    """HashMap + LRU list; TTL heap reserved for Phase 4."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._data = HashMap()
        self._lru = DoublyLinkedList()
        self._ttl_heap = MinHeap()
        self._metrics = StoreMetrics()

    def info_memory(self) -> StoreMetrics:
        """Return a copy of current memory metrics."""
        return StoreMetrics(
            used_memory=self._metrics.used_memory,
            maxmemory=self._metrics.maxmemory,
            evicted_keys=self._metrics.evicted_keys,
        )

    def _evict_entry(self, entry: Entry) -> None:
        """Remove *entry* from LRU and subtract its accounted bytes."""
        self._lru.remove_node(entry.lru_node)
        self._metrics.used_memory -= entry.entry_bytes

    def set(self, key: str, value: str) -> None:
        """Insert or replace *key* with *value*; update LRU and used_memory."""
        old = self._data.get(key)
        if isinstance(old, Entry):
            self._evict_entry(old)
        lru_node = self._lru.insert_front(key)
        entry_bytes = _utf8_len(key) + _utf8_len(value)
        entry = Entry(
            key=key,
            value=value,
            entry_bytes=entry_bytes,
            lru_node=lru_node,
        )
        self._data.put(key, entry)
        self._metrics.used_memory += entry_bytes

    def get(self, key: str) -> str | None:
        """Return value for *key*, or None; on hit, promote key in LRU."""
        raw = self._data.get(key)
        if not isinstance(raw, Entry):
            return None
        self._lru.move_to_front(raw.lru_node)
        return raw.value

    def delete(self, key: str) -> int:
        """Remove *key*; return 1 if existed else 0."""
        raw = self._data.get(key)
        if not isinstance(raw, Entry):
            return 0
        self._evict_entry(raw)
        self._data.remove(key)
        return 1

    def exists(self, key: str) -> int:
        """Return 1 if *key* exists, else 0."""
        return 1 if self._data.contains(key) else 0

    def dbsize(self) -> int:
        """Return number of keys."""
        return self._data.size()

    def keys(self) -> list[str]:
        """Return all keys in hashmap iteration order (unsorted)."""
        return list(self._data.keys())
