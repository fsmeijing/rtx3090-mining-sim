# -*- coding: utf-8 -*-
"""创世复算与 CPU Nonce 搜索测试。"""

import unittest

from bitcoin_pow.block_header import GENESIS_HASH_HEX, genesis_header
from bitcoin_pow.genesis import search_nonce, verify_genesis
from bitcoin_pow.sha256d import block_header_hash, to_display_hex
from bitcoin_pow.target import mode_target


class TestVerifyGenesis(unittest.TestCase):
    def test_genesis_recompute_exact(self):
        res = verify_genesis()
        self.assertTrue(res.match)
        self.assertEqual(res.hash_hex, GENESIS_HASH_HEX)
        self.assertEqual(len(res.hash_hex), 64)
        self.assertIn("MATCH", res.summary())

    def test_genesis_fields(self):
        res = verify_genesis()
        h = res.header
        self.assertEqual(h.version, 1)
        self.assertEqual(h.timestamp, 1231006505)
        self.assertEqual(h.nbits, 0x1D00FFFF)
        self.assertEqual(h.nonce, 2083236893)
        self.assertEqual(set(h.prev_hash_hex), {"0"})


class TestSearchNonce(unittest.TestCase):
    def test_genesis_nonce_is_a_solution(self):
        target, _ = __import__("bitcoin_pow.target", fromlist=["nbits_to_target"]) \
            .nbits_to_target(0x1D00FFFF)
        header = genesis_header()
        digest = block_header_hash(header.serialize())
        self.assertTrue(to_display_hex(digest) == GENESIS_HASH_HEX)
        # 已知创世 Nonce 一定满足 H <= T
        from bitcoin_pow.target import compare

        self.assertTrue(compare(digest, target))

    def test_max_target_hits_immediately(self):
        target = (1 << 256) - 1
        res = search_nonce(genesis_header(), target, start_nonce=777, max_attempts=10)
        self.assertTrue(res.found)
        self.assertEqual(res.nonce, 777)
        self.assertEqual(res.attempts, 1)

    def test_known_solution_found_first(self):
        """目标 = Nonce 500 的哈希，则搜索命中处 H<=T 且是首个命中。"""
        header = genesis_header()
        chosen = 500
        digest500 = block_header_hash(header.with_nonce(chosen).serialize())
        target = int.from_bytes(digest500, "little")   # 比特币小端解释
        res = search_nonce(header, target, start_nonce=0, max_attempts=100000)
        self.assertTrue(res.found)
        self.assertLessEqual(res.nonce, chosen)
        # 命中者必须是 [0, res.nonce] 内第一个满足 H<=T 的 Nonce
        for n in range(res.nonce):
            d = block_header_hash(header.with_nonce(n).serialize())
            self.assertGreater(int.from_bytes(d, "big"), target)

    def test_max_attempts_respected(self):
        res = search_nonce(
            genesis_header(), 0, start_nonce=0,
            max_attempts=50, end_nonce=1 << 32,
        )
        self.assertFalse(res.found)
        self.assertEqual(res.reason, "max-attempts")
        self.assertEqual(res.attempts, 50)

    def test_exhausted_range(self):
        res = search_nonce(
            genesis_header(), 0, start_nonce=100, max_attempts=None, end_nonce=160,
        )
        self.assertFalse(res.found)
        self.assertEqual(res.reason, "exhausted")
        self.assertEqual(res.attempts, 60)

    def test_deterministic(self):
        t = mode_target("easy")
        r1 = search_nonce(genesis_header(), t, start_nonce=0, max_attempts=10000)
        r2 = search_nonce(genesis_header(), t, start_nonce=0, max_attempts=10000)
        self.assertEqual((r1.found, r1.nonce, r1.hash_hex, r1.attempts),
                         (r2.found, r2.nonce, r2.hash_hex, r2.attempts))

    def test_easy_mode_finds_quickly(self):
        res = search_nonce(genesis_header(), mode_target("easy"),
                           start_nonce=0, max_attempts=1 << 20)
        self.assertTrue(res.found)
        self.assertLess(res.attempts, 100000)


if __name__ == "__main__":
    unittest.main()
