"""Tests for mini_redis.linked_list."""

from __future__ import annotations

import unittest

from mini_redis.linked_list import DoublyLinkedList, Node


class TestDoublyLinkedList(unittest.TestCase):
    # 빈 리스트에서 remove_front 시 예외가 나는지 확인한다.
    def test_remove_front_empty_raises(self) -> None:
        lst = DoublyLinkedList()
        with self.assertRaises(ValueError):
            lst.remove_front()

    # 빈 리스트에서 remove_back 시 예외가 나는지 확인한다.
    def test_remove_back_empty_raises(self) -> None:
        lst = DoublyLinkedList()
        with self.assertRaises(ValueError):
            lst.remove_back()

    # 단일 노드에서 insert/remove_front 동작과 빈 리스트 복귀를 검증한다.
    def test_single_node_insert_front_remove_front(self) -> None:
        lst = DoublyLinkedList()
        lst.insert_front("a")
        self.assertEqual(lst.remove_front(), "a")
        self.assertIsNone(lst.head)
        self.assertIsNone(lst.tail)

    # insert_back 한 뒤 remove_back으로 동일 데이터가 나오는지 검증한다.
    def test_single_node_insert_back_remove_back(self) -> None:
        lst = DoublyLinkedList()
        lst.insert_back("z")
        self.assertEqual(lst.remove_back(), "z")
        self.assertIsNone(lst.head)

    # 앞뒤 삽입 후 head→tail 순회 데이터가 기대와 같은지 검증한다.
    def test_insert_front_back_order(self) -> None:
        lst = DoublyLinkedList()
        lst.insert_back("b")
        lst.insert_front("a")
        lst.insert_back("c")
        self.assertEqual(list(lst.iter_data()), ["a", "b", "c"])

    # remove_node로 중간 노드를 제거해도 나머지 연결이 유지되는지 검증한다.
    def test_remove_node_middle(self) -> None:
        lst = DoublyLinkedList()
        lst.insert_back("a")
        n = lst.insert_back("b")
        lst.insert_back("c")
        lst.remove_node(n)
        self.assertEqual(list(lst.iter_data()), ["a", "c"])

    # remove_node로 head를 제거하면 새 head가 올바른지 검증한다.
    def test_remove_node_head(self) -> None:
        lst = DoublyLinkedList()
        n = lst.insert_front("x")
        lst.insert_back("y")
        lst.remove_node(n)
        self.assertEqual(list(lst.iter_data()), ["y"])

    # remove_node로 tail을 제거하면 tail 포인터가 갱신되는지 검증한다.
    def test_remove_node_tail(self) -> None:
        lst = DoublyLinkedList()
        lst.insert_back("x")
        n = lst.insert_back("y")
        lst.remove_node(n)
        self.assertEqual(lst.tail.data, "x")

    # head 노드에 대해 move_to_front가 no-op인지 검증한다.
    def test_move_to_front_already_head(self) -> None:
        lst = DoublyLinkedList()
        n = lst.insert_front("only")
        lst.move_to_front(n)
        self.assertIs(lst.head, n)

    # tail 노드를 move_to_front 한 뒤 순서가 MRU 순으로 바뀌는지 검증한다.
    def test_move_to_front_from_tail(self) -> None:
        lst = DoublyLinkedList()
        lst.insert_back("a")
        lst.insert_back("b")
        tail = lst.tail
        assert tail is not None
        lst.move_to_front(tail)
        self.assertEqual(list(lst.iter_data()), ["b", "a"])
        self.assertIs(lst.head, tail)

    # insert_front가 반환한 Node를 remove_node로 제거할 수 있는지 검증한다.
    def test_insert_front_returns_usable_node(self) -> None:
        lst = DoublyLinkedList()
        n: Node = lst.insert_front("data")
        self.assertEqual(n.data, "data")
        lst.remove_node(n)
        self.assertIsNone(lst.head)

    # 빈 리스트에서 remove_node 호출 시 예외가 나는지 검증한다.
    def test_remove_node_empty_raises(self) -> None:
        lst = DoublyLinkedList()
        orphan = Node("x")
        with self.assertRaises(ValueError):
            lst.remove_node(orphan)


if __name__ == "__main__":
    unittest.main()
