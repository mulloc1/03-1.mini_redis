"""Tests for mini_redis.hashmap."""

from __future__ import annotations

import unittest

from mini_redis.hashmap import HashMap, _fnv1a32


def _find_collision_pair(bucket_count: int = 16) -> tuple[str, str]:
    """같은 버킷 인덱스로 매핑되는 서로 다른 두 키를 탐색한다."""
    seen: dict[int, str] = {}
    for i in range(500_000):
        k = f"probe:{i}"
        idx = _fnv1a32(k) % bucket_count
        if idx in seen and seen[idx] != k:
            return seen[idx], k
        seen[idx] = k
    raise RuntimeError("collision pair not found (increase range)")


class TestHashMap(unittest.TestCase):
    # 존재하지 않는 키 get/remove는 None/False인지 검증한다.
    def test_get_remove_missing(self) -> None:
        m = HashMap()
        self.assertIsNone(m.get("nope"))
        self.assertFalse(m.remove("nope"))
        self.assertEqual(m.size(), 0)

    # put/get/contains/remove 기본 경로와 size 변화를 검증한다.
    def test_put_get_contains_remove(self) -> None:
        m = HashMap()
        m.put("a", 1)
        self.assertTrue(m.contains("a"))
        self.assertEqual(m.get("a"), 1)
        self.assertEqual(m.size(), 1)
        self.assertTrue(m.remove("a"))
        self.assertFalse(m.contains("a"))
        self.assertEqual(m.size(), 0)

    # 동일 키 put 시 값 갱신이 되고 size가 늘지 않는지 검증한다.
    def test_put_update_same_key_no_size_increase(self) -> None:
        m = HashMap()
        m.put("k", "v1")
        m.put("k", "v2")
        self.assertEqual(m.get("k"), "v2")
        self.assertEqual(m.size(), 1)

    # 충돌 버킷에 두 키를 넣어도 각각 조회되는지 검증한다.
    def test_chaining_two_keys_same_bucket(self) -> None:
        k1, k2 = _find_collision_pair(16)
        m = HashMap()
        m.put(k1, "v1")
        m.put(k2, "v2")
        self.assertEqual(m.get(k1), "v1")
        self.assertEqual(m.get(k2), "v2")
        self.assertEqual(m.size(), 2)
        self.assertTrue(m.remove(k1))
        self.assertIsNone(m.get(k1))
        self.assertEqual(m.get(k2), "v2")

    # 로드 팩터 초과 시 버킷이 2배로 늘고 모든 키가 유지되는지 검증한다.
    def test_resize_doubles_buckets_after_load_factor(self) -> None:
        m = HashMap()
        keys = [f"key:{i}" for i in range(13)]
        for k in keys:
            m.put(k, k)
        self.assertEqual(len(m._buckets), 32)
        self.assertEqual(m.size(), 13)
        for k in keys:
            self.assertEqual(m.get(k), k)

    # rehash 후에도 충돌 쌍이 각각 올바른 값을 갖는지 검증한다.
    def test_resize_preserves_colliding_entries(self) -> None:
        k1, k2 = _find_collision_pair(16)
        m = HashMap()
        fillers = [f"f:{i}" for i in range(11)]
        for fk in fillers:
            m.put(fk, fk)
        m.put(k1, "A")
        m.put(k2, "B")
        self.assertGreater(len(m._buckets), 16)
        self.assertEqual(m.get(k1), "A")
        self.assertEqual(m.get(k2), "B")

    # keys() 순회가 size와 일치하고 모든 키를 포함하는지 검증한다.
    def test_keys_covers_all_entries(self) -> None:
        m = HashMap()
        m.put("x", 1)
        m.put("y", 2)
        ks = set(m.keys())
        self.assertEqual(ks, {"x", "y"})
        self.assertEqual(len(ks), m.size())


if __name__ == "__main__":
    unittest.main()
