"""Tests for mini_redis.heap."""

from __future__ import annotations

import unittest

from mini_redis.heap import MinHeap


class TestMinHeap(unittest.TestCase):
    # 빈 힙에서 peek/pop 시 IndexError가 나는지 확인한다.
    def test_empty_peek_pop_raise(self) -> None:
        h = MinHeap()
        with self.assertRaises(IndexError):
            h.peek()
        with self.assertRaises(IndexError):
            h.pop()

    # 단일 push 후 peek/pop이 동일 원소를 반환하는지 검증한다.
    def test_single_element(self) -> None:
        h = MinHeap()
        h.push((1.0, "k"))
        self.assertEqual(h.peek(), (1.0, "k"))
        self.assertEqual(h.size(), 1)
        self.assertEqual(h.pop(), (1.0, "k"))
        self.assertEqual(h.size(), 0)

    # expire_at 오름차순으로 pop되는지 검증한다.
    def test_pop_order_by_expire_at(self) -> None:
        h = MinHeap()
        for t in [5.0, 1.0, 3.0]:
            h.push((t, f"k{t}"))
        self.assertEqual(h.pop(), (1.0, "k1.0"))
        self.assertEqual(h.pop(), (3.0, "k3.0"))
        self.assertEqual(h.pop(), (5.0, "k5.0"))

    # expire_at이 같을 때 두 번째 필드(key)로 tie-break 되는지 검증한다.
    def test_tie_breaker_key_tuple_order(self) -> None:
        h = MinHeap()
        h.push((1.0, "b"))
        h.push((1.0, "a"))
        first = h.pop()
        second = h.pop()
        self.assertEqual(first, (1.0, "a"))
        self.assertEqual(second, (1.0, "b"))

    # 같은 값을 여러 번 push해도 모두 pop되는지 검증한다.
    def test_duplicate_items(self) -> None:
        h = MinHeap()
        h.push((2.0, "x"))
        h.push((2.0, "x"))
        self.assertEqual(h.pop(), (2.0, "x"))
        self.assertEqual(h.pop(), (2.0, "x"))

    # 무작위 순서 push 후 전부 sorted 순으로 나오는지 검증한다.
    def test_many_random_push_pop_sorted(self) -> None:
        h = MinHeap()
        items = [(float(i), f"k{i}") for i in [9, 2, 7, 1, 5, 3, 8, 4, 6, 0]]
        for it in items:
            h.push(it)
        out: list[tuple[float, str]] = []
        while h.size():
            out.append(h.pop())
        self.assertEqual(out, sorted(items))


if __name__ == "__main__":
    unittest.main()
