# -*- coding: utf-8 -*-
"""SHA256d 参考实现测试（含 SHA-256 标准测试向量）。"""

import hashlib
import unittest

from bitcoin_pow.sha256d import (
    block_header_hash,
    from_display_hex,
    sha256,
    sha256d,
    to_display_hex,
)


class TestSha256(unittest.TestCase):
    def test_empty_string_vector(self):
        self.assertEqual(
            sha256(b"").hex(),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_abc_vector(self):
        self.assertEqual(
            sha256(b"abc").hex(),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_sha256d_matches_double_hashlib(self):
        for data in (b"", b"abc", b"\x00" * 80, bytes(range(256))):
            expect = hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()
            self.assertEqual(sha256d(data).hex(), expect)


class TestGenesisHash(unittest.TestCase):
    def test_genesis_hash_exact(self):
        from bitcoin_pow.block_header import genesis_header

        digest = block_header_hash(genesis_header().serialize())
        display = to_display_hex(digest)
        self.assertEqual(
            display,
            "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
        )
        self.assertEqual(len(display), 64)  # 完整 64 位十六进制字符

    def test_display_roundtrip(self):
        raw = bytes(range(32))
        self.assertEqual(from_display_hex(to_display_hex(raw)), raw)


if __name__ == "__main__":
    unittest.main()
