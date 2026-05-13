"""Doubly linked list for LRU chains and hashmap collision buckets."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


class Node:
    """List node with bidirectional links."""

    __slots__ = ("data", "next", "prev")

    def __init__(self, data: Any) -> None:
        self.prev: Node | None = None
        self.next: Node | None = None
        self.data: Any = data


class DoublyLinkedList:
    """Sentinel-free doubly linked list; front is the head end."""

    def __init__(self) -> None:
        self._head: Node | None = None
        self._tail: Node | None = None

    def insert_front(self, data: Any) -> Node:
        """Insert data at the head. Returns the new node (O(1))."""
        node = Node(data)
        if self._head is None:
            self._head = self._tail = node
            return node
        node.next = self._head
        self._head.prev = node
        self._head = node
        return node

    def insert_back(self, data: Any) -> Node:
        """Insert data at the tail. Returns the new node (O(1))."""
        node = Node(data)
        if self._tail is None:
            self._head = self._tail = node
            return node
        node.prev = self._tail
        self._tail.next = node
        self._tail = node
        return node

    def remove_front(self) -> Any:
        """Remove and return data at the head. Raises ValueError if empty."""
        if self._head is None:
            raise ValueError("remove_front from empty list")
        data = self._head.data
        if self._head is self._tail:
            self._head = self._tail = None
        else:
            assert self._head.next is not None
            self._head = self._head.next
            self._head.prev = None
        return data

    def remove_back(self) -> Any:
        """Remove and return data at the tail. Raises ValueError if empty."""
        if self._tail is None:
            raise ValueError("remove_back from empty list")
        data = self._tail.data
        if self._head is self._tail:
            self._head = self._tail = None
        else:
            assert self._tail.prev is not None
            self._tail = self._tail.prev
            self._tail.next = None
        return data

    def remove_node(self, node: Node) -> None:
        """Unlink a node known to belong to this list (O(1))."""
        if self._head is None:
            raise ValueError("remove_node from empty list")
        if node.prev is not None:
            node.prev.next = node.next
        else:
            self._head = node.next
        if node.next is not None:
            node.next.prev = node.prev
        else:
            self._tail = node.prev
        node.prev = node.next = None

    def move_to_front(self, node: Node) -> None:
        """Move an existing node to the head without changing data (O(1))."""
        if self._head is node:
            return
        self.remove_node(node)
        node.next = self._head
        node.prev = None
        if self._head is not None:
            self._head.prev = node
        else:
            self._tail = node
        self._head = node

    def iter_data(self) -> Iterator[Any]:
        """Yield data from head to tail."""
        cur = self._head
        while cur is not None:
            yield cur.data
            cur = cur.next

    @property
    def head(self) -> Node | None:
        return self._head

    @property
    def tail(self) -> Node | None:
        return self._tail
