"""Binary min-heap for (expire_at, key) TTL scheduling."""

from __future__ import annotations

class MinHeap:
    """Min-heap stored in a Python list; tuple order defines priority."""

    def __init__(self) -> None:
        self._data: list[tuple[float, str]] = []

    def size(self) -> int:
        return len(self._data)

    def push(self, item: tuple[float, str]) -> None:
        """Insert item and restore heap order."""
        self._data.append(item)
        self._heapify_up(len(self._data) - 1)

    def peek(self) -> tuple[float, str]:
        """Return the smallest item without removing it."""
        if not self._data:
            raise IndexError("peek on empty heap")
        return self._data[0]

    def pop(self) -> tuple[float, str]:
        """Remove and return the smallest item."""
        if not self._data:
            raise IndexError("pop from empty heap")
        root = self._data[0]
        last = self._data.pop()
        if self._data:
            self._data[0] = last
            self._heapify_down(0)
        return root

    def _parent(self, i: int) -> int:
        return (i - 1) // 2

    def _heapify_up(self, i: int) -> None:
        while i > 0:
            p = self._parent(i)
            if self._data[i] >= self._data[p]:
                break
            self._data[i], self._data[p] = self._data[p], self._data[i]
            i = p

    def _heapify_down(self, i: int) -> None:
        n = len(self._data)
        while True:
            smallest = i
            left = 2 * i + 1
            right = 2 * i + 2
            if left < n and self._data[left] < self._data[smallest]:
                smallest = left
            if right < n and self._data[right] < self._data[smallest]:
                smallest = right
            if smallest == i:
                break
            self._data[i], self._data[smallest] = self._data[smallest], self._data[i]
            i = smallest
