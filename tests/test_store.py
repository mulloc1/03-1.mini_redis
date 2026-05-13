"""Tests for Store string commands and used_memory accounting."""

from __future__ import annotations

import unittest

from mini_redis.errors import OOMError
from tests.helpers import FakeClock, make_store


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
        self.assertEqual(store.keys(), list(store._entries.keys()))


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


class TestStoreTTL(unittest.TestCase):
    def test_expire_missing_key_returns_zero(self) -> None:
        # EXPIRE on a missing key returns 0 and leaves metrics unchanged.
        clock = FakeClock()
        store = make_store(clock=clock)
        before = store.info_memory()
        self.assertEqual(store.expire("missing", 10), 0)
        after = store.info_memory()
        self.assertEqual(after.used_memory, before.used_memory)
        self.assertEqual(after.evicted_keys, before.evicted_keys)

    def test_expire_non_positive_seconds_deletes_existing_key(self) -> None:
        # EXPIRE with non-positive seconds immediately deletes existing keys.
        store = make_store(clock=FakeClock())
        store.set("a", "1")
        store.set("b", "2")
        self.assertEqual(store.expire("a", 0), 1)
        self.assertEqual(store.expire("b", -3), 1)
        self.assertEqual(store.dbsize(), 0)
        metrics = store.info_memory()
        self.assertEqual(metrics.used_memory, 0)
        self.assertEqual(metrics.evicted_keys, 0)

    def test_ttl_counts_down_with_ceil(self) -> None:
        # TTL returns remaining seconds rounded up for fractional time.
        clock = FakeClock(start=100.0)
        store = make_store(clock=clock)
        store.set("session", "abc")
        self.assertEqual(store.expire("session", 10), 1)
        self.assertEqual(store.ttl("session"), 10)
        clock.advance(2.0)
        self.assertEqual(store.ttl("session"), 8)
        clock.advance(0.5)
        self.assertEqual(store.ttl("session"), 8)

    def test_ttl_return_values_for_missing_no_ttl_and_ttl(self) -> None:
        # TTL returns -2 for missing, -1 for persistent, or remaining seconds.
        clock = FakeClock()
        store = make_store(clock=clock)
        self.assertEqual(store.ttl("missing"), -2)
        store.set("forever", "x")
        self.assertEqual(store.ttl("forever"), -1)
        store.expire("forever", 30)
        self.assertEqual(store.ttl("forever"), 30)

    def test_due_key_expires_on_public_commands(self) -> None:
        # Public commands sweep due TTL entries before answering.
        clock = FakeClock()
        store = make_store(clock=clock)
        store.set("a", "1")
        store.set("b", "2")
        store.expire("a", 5)
        clock.advance(5)
        self.assertEqual(store.exists("a"), 0)
        self.assertEqual(store.dbsize(), 1)
        self.assertEqual(store.keys(), ["b"])
        self.assertIsNone(store.get("a"))
        self.assertEqual(store.info_memory().evicted_keys, 0)

    def test_get_expired_key_does_not_promote_lru(self) -> None:
        # GET on an expired key deletes it without promoting it in the LRU list.
        clock = FakeClock()
        store = make_store(clock=clock)
        store.set("a", "1")
        store.set("b", "2")
        store.expire("a", 1)
        assert store._lru.head is not None
        assert store._lru.tail is not None
        self.assertEqual(store._lru.head.data, "b")
        self.assertEqual(store._lru.tail.data, "a")
        clock.advance(1)
        self.assertIsNone(store.get("a"))
        assert store._lru.head is not None
        assert store._lru.tail is not None
        self.assertEqual(store._lru.head.data, "b")
        self.assertEqual(store._lru.tail.data, "b")

    def test_expire_update_discards_stale_heap_entry(self) -> None:
        # Re-EXPIRE leaves the old heap record stale until a later sweep.
        clock = FakeClock()
        store = make_store(clock=clock)
        store.set("k", "v")
        store.expire("k", 10)
        clock.advance(5)
        store.expire("k", 20)
        clock.advance(6)
        self.assertEqual(store.exists("k"), 1)
        self.assertEqual(store.get("k"), "v")
        clock.advance(14)
        self.assertEqual(store.exists("k"), 0)

    def test_set_overwrite_clears_existing_ttl(self) -> None:
        # SET overwrite clears the previous TTL and leaves the new value persistent.
        clock = FakeClock()
        store = make_store(clock=clock)
        store.set("k", "v1")
        store.expire("k", 60)
        store.set("k", "v2")
        self.assertEqual(store.ttl("k"), -1)
        clock.advance(120)
        self.assertEqual(store.exists("k"), 1)
        self.assertEqual(store.get("k"), "v2")

    def test_delete_leaves_stale_heap_record_until_sweep(self) -> None:
        # DEL removes authoritative data while the stale heap record is swept later.
        clock = FakeClock()
        store = make_store(clock=clock)
        store.set("k", "v")
        store.expire("k", 10)
        self.assertEqual(store._ttl_heap.size(), 1)
        self.assertEqual(store.delete("k"), 1)
        self.assertEqual(store._ttl_heap.size(), 1)
        clock.advance(10)
        self.assertEqual(store.dbsize(), 0)
        self.assertEqual(store._ttl_heap.size(), 0)

    def test_ttl_expiration_can_avoid_lru_eviction_under_maxmemory(self) -> None:
        # Expiring due keys before SET can free memory without LRU eviction.
        clock = FakeClock()
        store = make_store(clock=clock)
        store.set_maxmemory(10)
        store.set("a", "1111")
        store.set("b", "2222")
        store.expire("a", 1)
        clock.advance(1)
        store.set("c", "3333")
        self.assertEqual(store.exists("a"), 0)
        self.assertEqual(store.exists("b"), 1)
        self.assertEqual(store.exists("c"), 1)
        self.assertEqual(store.info_memory().evicted_keys, 0)


if __name__ == "__main__":
    unittest.main()
