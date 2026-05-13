"""Tests for Store string commands and used_memory accounting."""

from __future__ import annotations

import unittest

from tests.helpers import make_store


class TestStore(unittest.TestCase):
    def test_set_then_get_returns_value(self) -> None:
        # SET then GET returns the stored string value.
        store = make_store()
        store.set("name", "Alice")
        self.assertEqual(store.get("name"), "Alice")

    def test_get_missing_returns_none(self) -> None:
        # GET on a missing key returns None.
        store = make_store()
        self.assertIsNone(store.get("missing"))

    def test_delete_returns_count(self) -> None:
        # DEL returns 1 once, then 0 for missing or already removed keys.
        store = make_store()
        store.set("k", "v")
        self.assertEqual(store.delete("k"), 1)
        self.assertEqual(store.delete("k"), 0)
        self.assertEqual(store.delete("none"), 0)

    def test_exists_after_delete(self) -> None:
        # EXISTS is 0 after the key is deleted.
        store = make_store()
        store.set("x", "1")
        self.assertEqual(store.exists("x"), 1)
        store.delete("x")
        self.assertEqual(store.exists("x"), 0)

    def test_dbsize_and_keys_snapshot(self) -> None:
        # DBSIZE matches key count; KEYS is a list snapshot of stored keys.
        store = make_store()
        store.set("user:1", "a")
        store.set("user:2", "b")
        self.assertEqual(store.dbsize(), 2)
        keys = store.keys()
        self.assertIsInstance(keys, list)
        self.assertEqual(len(keys), 2)
        self.assertEqual(set(keys), {"user:1", "user:2"})

    def test_used_memory_matches_utf8_sum(self) -> None:
        # used_memory equals sum of UTF-8 byte lengths of keys and values.
        store = make_store()
        k, v = "키", "한글"
        store.set(k, v)
        expected = len(k.encode("utf-8")) + len(v.encode("utf-8"))
        self.assertEqual(store.info_memory().used_memory, expected)

    def test_used_memory_on_overwrite(self) -> None:
        # Overwriting a key adjusts used_memory to the new entry size only.
        store = make_store()
        store.set("k", "ab")
        m1 = store.info_memory().used_memory
        store.set("k", "x")
        m2 = store.info_memory().used_memory
        self.assertEqual(m1, len("k".encode("utf-8")) + len("ab".encode("utf-8")))
        self.assertEqual(m2, len("k".encode("utf-8")) + len("x".encode("utf-8")))

    def test_used_memory_on_delete(self) -> None:
        # After DEL, used_memory returns to zero for an empty store.
        store = make_store()
        store.set("a", "b")
        self.assertGreater(store.info_memory().used_memory, 0)
        store.delete("a")
        self.assertEqual(store.info_memory().used_memory, 0)

    def test_lru_order_after_get(self) -> None:
        # GET promotes the key to MRU (list head); older key is at tail.
        store = make_store()
        store.set("a", "1")
        store.set("b", "2")
        store.get("a")
        assert store._lru.head is not None
        assert store._lru.tail is not None
        self.assertEqual(store._lru.head.data, "a")
        self.assertEqual(store._lru.tail.data, "b")

    def test_lru_order_after_overwrite(self) -> None:
        # Overwriting an existing key moves that key to MRU (head).
        store = make_store()
        store.set("a", "1")
        store.set("b", "2")
        store.set("a", "3")
        assert store._lru.head is not None
        assert store._lru.tail is not None
        self.assertEqual(store._lru.head.data, "a")
        self.assertEqual(store._lru.tail.data, "b")

    def test_keys_reflect_internal_iteration(self) -> None:
        # keys() matches HashMap.keys() iteration order (no sorting).
        store = make_store()
        store.set("x", "1")
        store.set("y", "2")
        self.assertEqual(store.keys(), list(store._data.keys()))


if __name__ == "__main__":
    unittest.main()
