"""Open-addressing-free hash map with chaining (doubly linked lists)."""

from __future__ import annotations

from collections.abc import Iterator

from mini_redis.linked_list import DoublyLinkedList, Node

_FNV_OFFSET = 2166136261
_FNV_PRIME = 16777619
_INITIAL_BUCKETS = 16
_LOAD_FACTOR_LIMIT = 0.75


def _fnv1a32(key: str) -> int:
    """FNV-1a 32-bit over UTF-8 bytes of key."""
    h = _FNV_OFFSET
    for b in key.encode("utf-8"):
        h ^= b
        h = (h * _FNV_PRIME) & 0xFFFFFFFF
    return h


class HashMap:
    """String-key map with separate chaining and dynamic rehashing."""

    def __init__(self) -> None:
        self._buckets: list[DoublyLinkedList | None] = [None] * _INITIAL_BUCKETS
        self._size = 0

    def _index(self, key: str) -> int:
        return _fnv1a32(key) % len(self._buckets)

    def _find_node(self, key: str) -> tuple[int, Node | None]:
        idx = self._index(key)
        chain = self._buckets[idx]
        if chain is None:
            return idx, None
        cur = chain.head
        while cur is not None:
            pair = cur.data
            if pair[0] == key:
                return idx, cur
            cur = cur.next
        return idx, None

    def _maybe_resize(self) -> None:
        if self._size == 0:
            return
        if self._size / len(self._buckets) <= _LOAD_FACTOR_LIMIT:
            return
        self._resize()

    def _resize(self) -> None:
        old_pairs: list[tuple[str, object]] = []
        for b in self._buckets:
            if b is None:
                continue
            for pair in b.iter_data():
                old_pairs.append((pair[0], pair[1]))
        new_len = len(self._buckets) * 2
        self._buckets = [None] * new_len
        self._size = 0
        for k, v in old_pairs:
            self.put(k, v)

    def put(self, key: str, value: object) -> None:
        """Insert or update key. Rehashes when load factor exceeds 0.75."""
        idx, node = self._find_node(key)
        chain = self._buckets[idx]
        if node is not None:
            node.data = (key, value)
            return
        if chain is None:
            chain = DoublyLinkedList()
            self._buckets[idx] = chain
        chain.insert_front((key, value))
        self._size += 1
        self._maybe_resize()

    def get(self, key: str) -> object | None:
        """Return the value for key, or None if the key is absent."""
        _, node = self._find_node(key)
        if node is None:
            return None
        return node.data[1]

    def remove(self, key: str) -> bool:
        """Remove the key; return True if an entry existed."""
        idx, node = self._find_node(key)
        if node is None:
            return False
        chain = self._buckets[idx]
        assert chain is not None
        chain.remove_node(node)
        if chain.head is None:
            self._buckets[idx] = None
        self._size -= 1
        return True

    def contains(self, key: str) -> bool:
        """Return True if key is present."""
        return self._find_node(key)[1] is not None

    def keys(self) -> Iterator[str]:
        """Iterate keys in bucket order, head-to-tail within each chain."""
        for b in self._buckets:
            if b is None:
                continue
            for pair in b.iter_data():
                yield pair[0]

    def size(self) -> int:
        """Return the number of stored keys."""
        return self._size
