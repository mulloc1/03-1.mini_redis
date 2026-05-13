"""Tests for Store string commands and used_memory accounting."""

from __future__ import annotations

import unittest

from mini_redis.errors import OOMError
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


class TestStoreEviction(unittest.TestCase):
    def test_set_maxmemory_zero_is_unlimited(self) -> None:
        # maxmemory=0 keeps unlimited mode and never increments evicted_keys.
        store = make_store()
        store.set_maxmemory(0)
        for i in range(20):
            store.set(f"k{i}", "value")
        metrics = store.info_memory()
        self.assertEqual(metrics.maxmemory, 0)
        self.assertEqual(metrics.evicted_keys, 0)
        self.assertEqual(store.dbsize(), 20)

    def test_set_maxmemory_negative_raises(self) -> None:
        # Negative maxmemory is rejected at store layer.
        store = make_store()
        with self.assertRaises(ValueError):
            store.set_maxmemory(-1)

    def test_set_evicts_lru_back_when_exceeded(self) -> None:
        # LRU tail key is evicted first when SET pushes used_memory over limit.
        store = make_store()
        store.set_maxmemory(16)
        store.set("a", "xxxx")
        store.set("b", "yyyy")
        store.set("c", "zzzz")
        self.assertEqual(store.get("a"), "xxxx")
        store.set("d", "wwww")
        self.assertEqual(store.exists("b"), 0)
        self.assertEqual(store.exists("a"), 1)
        self.assertEqual(store.exists("c"), 1)
        self.assertEqual(store.exists("d"), 1)
        self.assertEqual(store.info_memory().evicted_keys, 1)

    def test_eviction_continues_until_under_limit(self) -> None:
        # Eviction loop removes multiple keys until memory returns under limit.
        store = make_store()
        store.set_maxmemory(10)
        store.set("a", "123")
        store.set("b", "123")
        store.set("c", "123")
        store.set("d", "123")
        metrics = store.info_memory()
        self.assertLessEqual(metrics.used_memory, metrics.maxmemory)
        self.assertGreaterEqual(metrics.evicted_keys, 2)

    def test_evicted_keys_accumulates(self) -> None:
        # evicted_keys tracks cumulative number of LRU-policy evictions.
        store = make_store()
        store.set_maxmemory(12)
        store.set("a", "xxxx")
        store.set("b", "yyyy")
        store.set("c", "zzzz")
        first = store.info_memory().evicted_keys
        store.set("d", "wwww")
        second = store.info_memory().evicted_keys
        self.assertGreaterEqual(first, 1)
        self.assertGreater(second, first)

    def test_single_entry_over_maxmemory_raises_oom(self) -> None:
        # A single oversized entry is rejected with OOM and no mutation.
        store = make_store()
        store.set_maxmemory(4)
        with self.assertRaises(OOMError):
            store.set("hello", "world")
        self.assertEqual(store.dbsize(), 0)
        self.assertEqual(store.info_memory().used_memory, 0)

    def test_oom_does_not_mutate_existing_state(self) -> None:
        # OOM during SET preserves existing keys, memory, and LRU order.
        store = make_store()
        store.set_maxmemory(7)
        store.set("a", "1111")
        before_memory = store.info_memory().used_memory
        assert store._lru.head is not None
        before_head = store._lru.head.data
        with self.assertRaises(OOMError):
            store.set("hello", "world")
        self.assertEqual(store.get("a"), "1111")
        self.assertEqual(store.info_memory().used_memory, before_memory)
        assert store._lru.head is not None
        self.assertEqual(store._lru.head.data, before_head)

    def test_config_set_maxmemory_below_usage_evicts(self) -> None:
        # Lowering maxmemory below current usage triggers immediate eviction.
        store = make_store()
        store.set("a", "xxxx")
        store.set("b", "yyyy")
        self.assertEqual(store.dbsize(), 2)
        store.set_maxmemory(5)
        metrics = store.info_memory()
        self.assertEqual(store.dbsize(), 1)
        self.assertLessEqual(metrics.used_memory, metrics.maxmemory)
        self.assertEqual(metrics.evicted_keys, 1)


if __name__ == "__main__":
    unittest.main()
