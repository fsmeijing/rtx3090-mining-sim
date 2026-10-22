# -*- coding: utf-8 -*-
"""创世区块复算与 CPU 挖矿循环（CPU 参考实现）。"""

from __future__ import annotations

from dataclasses import dataclass

from .block_header import (
    GENESIS_HASH_HEX,
    BlockHeader,
    genesis_header,
)
from .sha256d import block_header_hash, to_display_hex
from .target import compare, diff_int, nbits_to_target, target_to_hex


@dataclass
class VerifyResult:
    """创世区块复算结果。"""

    header: BlockHeader
    hash_hex: str          # 完整 64 位十六进制展示
    expected_hex: str
    match: bool

    def summary(self) -> str:
        status = "MATCH" if self.match else "MISMATCH"
        return (
            "创世区块复算\n"
            "  计算 H      = %s\n"
            "  期望哈希    = %s\n"
            "  比对结果    = %s\n"
            "  完整性      = 256 bit / 64 hex chars" % (
                self.hash_hex, self.expected_hex, status)
        )


def verify_genesis(header: BlockHeader | None = None) -> VerifyResult:
    """复算创世区块：SHA256(SHA256(80B header)) 并与已知哈希比对。"""
    h = header or genesis_header()
    digest = block_header_hash(h.serialize())
    hash_hex = to_display_hex(digest)
    return VerifyResult(
        header=h,
        hash_hex=hash_hex,
        expected_hex=GENESIS_HASH_HEX,
        match=hash_hex == GENESIS_HASH_HEX,
    )


@dataclass
class SearchResult:
    """CPU Nonce 搜索结果。"""

    found: bool
    nonce: int | None
    hash_hex: str | None
    target: int
    attempts: int
    reason: str            # "found" | "exhausted" | "max-attempts"


def search_nonce(
    header_template: BlockHeader,
    target: int,
    start_nonce: int = 0,
    max_attempts: int | None = None,
    end_nonce: int = 1 << 32,
) -> SearchResult:
    """CPU 逐个尝试 Nonce：修改 -> 双 SHA-256 -> 完整整数比较。

    安全边界：受 max_attempts 与 Nonce 空间 [start, end) 双重限制。
    """
    attempts = 0
    nonce = start_nonce
    while nonce < end_nonce:
        if max_attempts is not None and attempts >= max_attempts:
            return SearchResult(False, None, None, target, attempts, "max-attempts")
        digest = block_header_hash(header_template.with_nonce(nonce).serialize())
        attempts += 1
        if compare(digest, target):
            return SearchResult(
                True, nonce, to_display_hex(digest), target, attempts, "found"
            )
        nonce += 1
    return SearchResult(False, None, None, target, attempts, "exhausted")


def difficulty_description(nbits: int) -> str:
    """人读的难度说明（目标十六进制 + 前导零比特数）。"""
    target, non_canonical = nbits_to_target(nbits)
    mark = "（非规范 mantissa）" if non_canonical else ""
    return "nBits=0x%08x%s T=%s 前导零=%d bit" % (
        nbits, mark, target_to_hex(target), leading_zero_bits(target),
    )


def hash_int_hex(hash_hex_display: str) -> str:
    """展示序哈希的 256-bit 整数值（十六进制，教学展示用）。

    展示序十六进制本身就是整数的常规写法（小端摘要 => 大端展示）。
    """
    return "%064x" % int(hash_hex_display, 16)
