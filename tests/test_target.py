# -*- coding: utf-8 -*-
"""nBits 解码与完整 256-bit 目标比较测试。"""

import unittest

from bitcoin_pow.target import (
    GENESIS_TARGET,
    MODE_EASY,
    MODE_GENESIS,
    MODE_MEDIUM,
    compare,
    leading_zero_bits,
    mode_shift_bits,
    mode_target,
    nbits_to_target,
    target_to_hex,
)


class TestNBits(unittest.TestCase):
    def test_genesis_nbits(self):
        target, non_canonical = nbits_to_target(0x1D00FFFF)
        self.assertFalse(non_canonical)
        self.assertEqual(
            target,
            0x00000000FFFF0000000000000000000000000000000000000000000000000000,
        )
        self.assertEqual(target, GENESIS_TARGET)

    def test_target_hex_is_64_chars(self):
        self.assertEqual(len(target_to_hex(GENESIS_TARGET)), 64)
        self.assertEqual(
            target_to_hex(GENESIS_TARGET),
            "00000000ffff0000000000000000000000000000000000000000000000000000",
        )

    def test_non_canonical_mantissa_flagged(self):
        _, flag = nbits_to_target(0x1D800123)
        self.assertTrue(flag)

    def test_small_exponent(self):
        # exponent=0x03, mantissa=0x010234 -> 直接等于尾数（>>8*(3-3)=0 移位）
        target, _ = nbits_to_target(0x03010234)
        self.assertEqual(target, 0x010234)
        target2, _ = nbits_to_target(0x02010000)
        self.assertEqual(target2, 0x010000 >> 8)  # exponent<3 时右移


class TestCompare(unittest.TestCase):
    """compare() 输入为协议序摘要（SHA-256 原始输出），按小端解释为整数。

    即：整数 = int(展示序十六进制, 16) = int.from_bytes(digest, "little")。
    """

    def setUp(self):
        self.t = 0x00000000FFFF0000000000000000000000000000000000000000000000000000

    @staticmethod
    def digest_for(value: int) -> bytes:
        """构造协议序摘要字节，使其按小端解释后等于 value。"""
        return value.to_bytes(32, "little")

    def test_equal_passes(self):
        self.assertTrue(compare(self.digest_for(self.t), self.t))     # H == T 也算满足

    def test_minus_one_passes(self):
        self.assertTrue(compare(self.digest_for(self.t - 1), self.t))

    def test_plus_one_fails(self):
        self.assertFalse(compare(self.digest_for(self.t + 1), self.t))  # 仅差 1 也必须判负

    def test_max_hash_fails(self):
        self.assertFalse(compare(b"\xff" * 32, self.t))

    def test_genesis_display_int_consistency(self):
        """展示序十六进制 == 整数值（小端解释）。"""
        from bitcoin_pow.block_header import GENESIS_HASH_HEX

        digest = bytes.fromhex(GENESIS_HASH_HEX)[::-1]   # 展示序 -> 协议序
        self.assertEqual(int(GENESIS_HASH_HEX, 16), int.from_bytes(digest, "little"))
        self.assertTrue(compare(digest, self.t))

    def test_no_prefix_shortcut(self):
        """完整 256-bit 比较：高位相同必须看低位，绝不只看前缀。"""
        t = 0x1122000000000000000000000000000000000000000000000000000000000000
        self.assertTrue(compare(self.digest_for(t - 1), t))
        self.assertTrue(compare(self.digest_for(t), t))
        self.assertFalse(compare(self.digest_for(t + 1), t))   # 仅末位差 1 也判负


class TestModes(unittest.TestCase):
    def test_mode_ordering(self):
        """目标左移 => 目标更大 => 更容易命中；但目标自身前导零变少。"""
        easy = mode_target(MODE_EASY)
        medium = mode_target(MODE_MEDIUM)
        genesis = mode_target(MODE_GENESIS)
        self.assertGreater(easy, medium)
        self.assertGreater(medium, genesis)
        self.assertEqual(genesis, GENESIS_TARGET)
        # 前导零与难度方向相反：目标越大（越容易）前导零越少
        self.assertLess(leading_zero_bits(easy), leading_zero_bits(medium))
        self.assertLess(leading_zero_bits(medium), leading_zero_bits(genesis))
        self.assertEqual(mode_shift_bits(MODE_EASY), 24)
        self.assertEqual(mode_shift_bits(MODE_MEDIUM), 12)
        self.assertEqual(mode_shift_bits(MODE_GENESIS), 0)

    def test_expected_attempts_ordering(self):
        """命中概率：easy 约 2^8 次，medium 约 2^20 次，genesis 约 2^32 次。"""
        self.assertEqual(1 << 24, mode_target(MODE_EASY) // GENESIS_TARGET)
        self.assertEqual(1 << 12, mode_target(MODE_MEDIUM) // GENESIS_TARGET)

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            mode_target("hard")


if __name__ == "__main__":
    unittest.main()
