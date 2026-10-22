# -*- coding: utf-8 -*-
"""高度 0–19 真实区块测试向量测试。"""

import unittest

from bitcoin_pow.block_header import BlockHeader
from bitcoin_pow.real_blocks import load_real_blocks, source_metadata
from bitcoin_pow.sha256d import block_header_hash, to_display_hex
from bitcoin_pow.target import nbits_to_target


class TestRealBlocks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blocks = load_real_blocks()

    def test_twenty_blocks_loaded(self):
        self.assertEqual(len(self.blocks), 20)
        self.assertEqual([b.height for b in self.blocks], list(range(20)))
        self.assertEqual(source_metadata()["count"], 20)

    def test_all_hashes_recompute(self):
        """20 个真实区块头全部复算通过（CPU 独立验证）。"""
        for b in self.blocks:
            raw = bytes.fromhex(b.raw_header_hex)
            self.assertEqual(len(raw), 80, "height %d" % b.height)
            # 字段解码与 raw 头自洽
            parsed = BlockHeader.parse(raw)
            self.assertEqual(parsed.version, b.version, "height %d" % b.height)
            self.assertEqual(parsed.merkle_root_hex, b.merkle_root_hex, "height %d" % b.height)
            self.assertEqual(parsed.nonce, b.nonce, "height %d" % b.height)
            # SHA256d 复算
            got = to_display_hex(block_header_hash(raw))
            self.assertEqual(got, b.hash_hex, "height %d 复算不一致" % b.height)
            # 前后链接
            if b.height > 0:
                prev = self.blocks[b.height - 1]
                self.assertEqual(b.prev_hash_hex, prev.hash_hex,
                                 "height %d prev 链接错误" % b.height)

    def test_genesis_vector_exact(self):
        b0 = self.blocks[0]
        self.assertEqual(b0.version, 1)
        self.assertEqual(b0.timestamp, 1231006505)
        self.assertEqual(b0.nbits, 0x1D00FFFF)
        self.assertEqual(b0.nonce, 2083236893)
        self.assertEqual(
            b0.hash_hex,
            "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
        )

    def test_difficulty_unchanged_in_early_blocks(self):
        for b in self.blocks:
            target, _ = nbits_to_target(b.nbits)
            self.assertEqual(b.nbits, 0x1D00FFFF, "height %d" % b.height)

    def test_hashes_are_valid_pow(self):
        """每个区块哈希都满足 H <= T（真实 PoW）。"""
        for b in self.blocks:
            target, _ = nbits_to_target(b.nbits)
            # 展示序哈希本身就是大端整数的十六进制
            h = int(b.hash_hex, 16)
            self.assertLessEqual(h, target, "height %d 不满足 H<=T" % b.height)


if __name__ == "__main__":
    unittest.main()
