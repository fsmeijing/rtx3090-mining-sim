# -*- coding: utf-8 -*-
"""80 字节区块头序列化测试。"""

import unittest

from bitcoin_pow.block_header import (
    GENESIS_NONCE,
    HEADER_SIZE,
    BlockHeader,
    genesis_header,
)


class TestSerialize(unittest.TestCase):
    def test_genesis_header_is_80_bytes(self):
        raw = genesis_header().serialize()
        self.assertEqual(len(raw), HEADER_SIZE)
        self.assertEqual(len(raw.hex()), 160)

    def test_genesis_header_prefix_and_suffix(self):
        raw = genesis_header().serialize()
        self.assertTrue(raw.hex().startswith("01000000"))
        # Nonce 2083236893 = 0x7c2bac1d，小端写入 -> 1dac2b7c
        self.assertTrue(raw.hex().endswith("1dac2b7c"))

    def test_genesis_known_raw_header(self):
        """与 blockstream API 返回的真实创世头逐字节一致。"""
        expected = (
            "01000000000000000000000000000000000000000000000000000000000000000000"
            "00003ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
            "29ab5f49ffff001d1dac2b7c"
        )
        self.assertEqual(genesis_header().serialize().hex(), expected)

    def test_roundtrip_parse(self):
        header = genesis_header()
        parsed = BlockHeader.parse(header.serialize())
        self.assertEqual(parsed, header)

    def test_display_hex_roundtrip(self):
        h = genesis_header()
        raw = h.serialize()
        back = BlockHeader.parse(raw)
        self.assertEqual(back.merkle_root_hex, h.merkle_root_hex)
        self.assertEqual(back.prev_hash_hex, h.prev_hash_hex)

    def test_nonce_change_only_last_4_bytes(self):
        h0 = genesis_header(nonce=0).serialize()
        h1 = genesis_header(nonce=GENESIS_NONCE).serialize()
        self.assertEqual(h0[:76], h1[:76])
        self.assertNotEqual(h0[76:], h1[76:])

    def test_with_nonce_returns_new_object(self):
        h = genesis_header()
        h2 = h.with_nonce(123)
        self.assertEqual(h2.nonce, 123)
        self.assertEqual(h.nonce, GENESIS_NONCE)  # 原对象不变
        self.assertEqual(h2.version, h.version)
        self.assertEqual(h2.merkle_root_hex, h.merkle_root_hex)

    def test_invalid_fields_rejected(self):
        with self.assertRaises(ValueError):
            genesis_header(nonce=1 << 32)
        with self.assertRaises(ValueError):
            BlockHeader(1, "xyz", "00" * 32, 0, 0x1D00FFFF, 0)
        with self.assertRaises(ValueError):
            BlockHeader(1, "00" * 32, "00" * 31, 0, 0x1D00FFFF, 0)

    def test_wrong_parse_length(self):
        with self.assertRaises(ValueError):
            BlockHeader.parse(b"\x00" * 79)


if __name__ == "__main__":
    unittest.main()
