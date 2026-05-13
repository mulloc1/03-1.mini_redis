"""In-memory key-value store: string commands, LRU wiring, memory accounting."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil

from mini_redis.errors import OOMError
from mini_redis.hashmap import HashMap
from mini_redis.heap import MinHeap
from mini_redis.linked_list import DoublyLinkedList, Node


def _utf8_len(s: str) -> int:
    """Return byte length of *s* encoded as UTF-8."""
    return len(s.encode("utf-8"))


@dataclass(slots=True)
class Entry:
    """Stored key-value with cached byte size, LRU node, and optional TTL."""

    key: str
    value: str
    entry_bytes: int
    lru_node: Node
    expire_at: float | None = None


@dataclass(slots=True)
class StoreMetrics:
    """Snapshot fields aligned with INFO memory (subject §4.3)."""

    used_memory: int = 0
    maxmemory: int = 0
    evicted_keys: int = 0


class Store:
    """HashMap + LRU list + min-heap TTL scheduler."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._entries = HashMap()
        self._lru = DoublyLinkedList()
        self._ttl_heap = MinHeap()
        self._metrics = StoreMetrics()

    def info_memory(self) -> StoreMetrics:
        """Return a copy of current memory metrics."""
        self._expire_due()
        return StoreMetrics(
            used_memory=self._metrics.used_memory,
            maxmemory=self._metrics.maxmemory,
            evicted_keys=self._metrics.evicted_keys,
        )

    def _evict_entry(self, entry: Entry) -> None:
        """Remove *entry* from LRU and subtract its accounted bytes."""
        self._lru.remove_node(entry.lru_node)
        self._metrics.used_memory -= entry.entry_bytes

    def _remove_entry(self, key: str, entry: Entry) -> None:
        """Remove an entry from all authoritative store structures."""
        self._evict_entry(entry)
        self._entries.remove(key)

    def _expire_due(self) -> None:
        """Expire all due TTL heap entries, discarding stale heap records."""
        now = self._clock()
        while self._ttl_heap.size() > 0:
            expire_at, key = self._ttl_heap.peek()
            if expire_at > now:
                break
            self._ttl_heap.pop()
            raw = self._entries.get(key)
            if not isinstance(raw, Entry):
                continue
            if raw.expire_at != expire_at:
                continue
            self._remove_entry(key, raw)

    def _enforce_maxmemory(self) -> None:
        """Evict least recently used keys until used_memory <= maxmemory."""
        while (
            self._metrics.maxmemory > 0
            and self._metrics.used_memory > self._metrics.maxmemory
        ):
            if self._lru.tail is None:
                break
            evicted_key = self._lru.remove_back()
            raw = self._entries.get(evicted_key)
            assert isinstance(raw, Entry)
            self._metrics.used_memory -= raw.entry_bytes
            self._entries.remove(evicted_key)
            self._metrics.evicted_keys += 1

    def set_maxmemory(self, bytes_: int) -> None:
        """Set maxmemory in bytes; 0 means unlimited."""
        self._expire_due()
        if bytes_ < 0:
            raise ValueError("maxmemory must be non-negative")
        self._metrics.maxmemory = bytes_
        self._enforce_maxmemory()

    def set(self, key: str, value: str) -> None:
        """Insert or replace *key* with *value*; update LRU and used_memory."""
        self._expire_due()
        entry_bytes = _utf8_len(key) + _utf8_len(value)
        if self._metrics.maxmemory > 0 and entry_bytes > self._metrics.maxmemory:
            raise OOMError("entry exceeds maxmemory")
        old = self._entries.get(key)
        if isinstance(old, Entry):
            self._evict_entry(old)
        lru_node = self._lru.insert_front(key)
        entry = Entry(
            key=key,
            value=value,
            entry_bytes=entry_bytes,
            lru_node=lru_node,
        )
        self._entries.put(key, entry)
        self._metrics.used_memory += entry_bytes
        self._enforce_maxmemory()

    def get(self, key: str) -> str | None:
        """Return value for *key*, or None; on hit, promote key in LRU."""
        self._expire_due()
        raw = self._entries.get(key)
        if not isinstance(raw, Entry):
            return None
        self._lru.move_to_front(raw.lru_node)
        return raw.value

    def delete(self, key: str) -> int:
        """Remove *key*; return 1 if existed else 0."""
        self._expire_due()
        raw = self._entries.get(key)
        if not isinstance(raw, Entry):
            return 0
        self._remove_entry(key, raw)
        return 1

    def exists(self, key: str) -> int:
        """Return 1 if *key* exists, else 0."""
        self._expire_due()
        return 1 if self._entries.contains(key) else 0

    def dbsize(self) -> int:
        """Return number of keys."""
        self._expire_due()
        return self._entries.size()

    def keys(self) -> list[str]:
        """Return all keys in hashmap iteration order (unsorted)."""
        self._expire_due()
        return list(self._entries.keys())

    def expire(self, key: str, seconds: int) -> int:
        """Set key TTL in seconds; return 1 if updated, else 0."""
        self._expire_due()
        raw = self._entries.get(key)
        if not isinstance(raw, Entry):
            return 0
        if seconds <= 0:
            self._remove_entry(key, raw)
            return 1
        expire_at = self._clock() + seconds
        raw.expire_at = expire_at
        self._ttl_heap.push((expire_at, key))
        return 1

    def ttl(self, key: str) -> int:
        """Return remaining TTL: -2 missing, -1 no TTL, or seconds remaining."""
        self._expire_due()
        raw = self._entries.get(key)
        if not isinstance(raw, Entry):
            return -2
        if raw.expire_at is None:
            return -1
        return max(0, ceil(raw.expire_at - self._clock()))
