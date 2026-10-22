# -*- coding: utf-8 -*-
"""nBits 目标解码与完整 256-bit 整数比较（CPU 参考实现）。

nBits 是 4 字节"压缩格式"目标：
    1 字节指数 exponent + 3 字节尾数 mantissa
    T = mantissa × 256^(exponent - 3)

创世区块 nBits = 0x1d00ffff：
    exponent = 0x1d = 29，mantissa = 0x00ffff
    T = 0xffff × 256^26 = 0x00000000FFFF0000...0000（共 64 位十六进制）

工作量证明判定：H 的 256-bit 整数值 ≤ T 的 256-bit 整数值。
本模块刻意使用 Python 任意精度整数做"完整比较"，
绝不采用"只看前导零个数"的捷径（后者只是教学直觉，不是共识规则）。
"""

from __future__ import annotations

# 创世目标（nBits=0x1d00ffff 解码结果）
GENESIS_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000

# 教学难度模式：在创世目标基础上左移，前导零更多 => 更容易命中
MODE_EASY = "easy"        # T_genesis << 24 （前 24 位更容易，约 2^24 倍概率）
MODE_MEDIUM = "medium"    # T_genesis << 12
MODE_GENESIS = "genesis"  # 原始创世目标（真实难度，无法在课堂上挖出）


class NonCanonicalNBitsWarning(UserWarning):
    """mantissa 最高位 ≥ 0x80（历史上表示负目标，现代共识不会出现）。"""


def nbits_to_target(nbits: int) -> tuple[int, bool]:
    """解码 nBits -> (256-bit 目标整数, 是否非规范)。

    非规范：mantissa 最高位为 1（0x800000 位），原始共识中表示负数。
    """
    if not 0 <= nbits <= 0xFFFFFFFF:
        raise ValueError("nBits 超出 uint32: %r" % nbits)
    exponent = nbits >> 24
    mantissa = nbits & 0x00FFFFFF
    non_canonical = bool(mantissa & 0x800000)
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    return target, non_canonical


def target_to_hex(target: int) -> str:
    """完整 64 位十六进制展示（不足补零）。"""
    if target < 0:
        raise ValueError("目标不能为负")
    if target >= 1 << 256:
        raise ValueError("目标超出 256 bit")
    return "%064x" % target


def leading_zero_bits(target: int) -> int:
    """目标的二进制前导零个数（教学观察用）。"""
    if target == 0:
        return 256
    return 256 - target.bit_length()


def mode_target(mode: str) -> int:
    """返回教学难度模式对应的完整目标值。"""
    if mode == MODE_EASY:
        return GENESIS_TARGET << 24
    if mode == MODE_MEDIUM:
        return GENESIS_TARGET << 12
    if mode == MODE_GENESIS:
        return GENESIS_TARGET
    raise ValueError("未知模式: %r（可选 easy/medium/genesis）" % mode)


def mode_shift_bits(mode: str) -> int:
    """模式相对创世目标的左移位数。"""
    return {MODE_EASY: 24, MODE_MEDIUM: 12, MODE_GENESIS: 0}[mode]


def compare(hash256: bytes, target: int) -> bool:
    """完整 256-bit 无符号整数比较：H <= T。

    比特币共识把 32 字节 SHA-256 输出（协议序）解释为小端 256-bit 整数，
    即"展示序十六进制（区块浏览器方向）才是整数的常规写法"：
        H_value = int.from_bytes(digest, "little") == int(display_hex, 16)

    本函数不采用任何"只看前导零"的捷径，完整比较 256 bit。
    """
    if not 0 <= target < (1 << 256):
        raise ValueError("目标必须是 0..2^256-1 的整数")
    if len(hash256) != 32:
        raise ValueError("哈希必须为 32 字节")
    h = int.from_bytes(hash256, "little")   # 比特币：协议序摘要按小端解释
    return h <= target


def diff_int(hash256: bytes) -> int:
    """哈希的 256-bit 整数值（教学展示用）。

    与 compare() 保持一致的小端整数语义：比特币把协议序摘要按小端
    解释为 256-bit 整数，即整数值 == int(展示序十六进制, 16)。
    """
    if len(hash256) != 32:
        raise ValueError("哈希必须为 32 字节")
    return int.from_bytes(hash256, "little")
