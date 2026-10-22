# -*- coding: utf-8 -*-
"""80 字节比特币区块头序列化（CPU 参考实现）。

区块头 6 个字段（共 80 字节，全部按协议小端序写入）：
    | 字段       | 大小 | 说明                                   |
    |-----------|-----|----------------------------------------|
    | Version   |  4B | 版本号                                  |
    | PrevHash  | 32B | 前一个区块哈希（协议序=展示序的字节倒序）      |
    | MerkleRoot| 32B | 交易默克尔根（同上）                      |
    | Timestamp |  4B | Unix 时间戳                              |
    | nBits     |  4B | 压缩难度目标                             |
    | Nonce     |  4B | 工作量证明随机数（4294967296 种取值）        |

字节序约定：
- 内部序列化使用"协议字节序"（比特币 P2P 网络上的真实字节）。
- 对外展示使用"大端十六进制"（与区块浏览器、blockstream 一致）。
  对哈希而言，展示序 = 协议序整串字节倒序（[::-1]）。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER_SIZE = 80

# 创世区块真实数据（比特币主网，2009-01-03）
GENESIS_VERSION = 1
GENESIS_PREV_HASH_HEX = "00" * 32
GENESIS_MERKLE_ROOT_HEX = (
    "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"
)
GENESIS_TIMESTAMP = 1231006505
GENESIS_NBITS = 0x1D00FFFF
GENESIS_NONCE = 2083236893
GENESIS_HASH_HEX = (
    "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
)


class FieldRangeError(ValueError):
    """字段超出 uint32/256-bit 范围。"""


def _check_u32(value: int, name: str) -> int:
    if not 0 <= value <= 0xFFFFFFFF:
        raise FieldRangeError("%s 超出 uint32 范围: %r" % (name, value))
    return value


def _check_hash256(hex_str: str, name: str) -> str:
    if len(hex_str) != 64:
        raise FieldRangeError("%s 必须是 64 个十六进制字符: %r" % (name, hex_str))
    int(hex_str, 16)  # 合法性检查
    return hex_str.lower()


@dataclass
class BlockHeader:
    """80 字节区块头。prev_hash/merkle_root 使用大端展示十六进制。"""

    version: int
    prev_hash_hex: str
    merkle_root_hex: str
    timestamp: int
    nbits: int
    nonce: int

    def __post_init__(self) -> None:
        _check_u32(self.version, "version")
        _check_u32(self.timestamp, "timestamp")
        _check_u32(self.nbits, "nbits")
        _check_u32(self.nonce, "nonce")
        self.prev_hash_hex = _check_hash256(self.prev_hash_hex, "prev_hash")
        self.merkle_root_hex = _check_hash256(self.merkle_root_hex, "merkle_root")

    # ------------------------------------------------------------------
    # 序列化 / 反序列化
    # ------------------------------------------------------------------
    def serialize(self) -> bytes:
        """序列化为 80 字节协议字节序区块头。"""
        prev_proto = bytes.fromhex(self.prev_hash_hex)[::-1]   # 展示序 -> 协议序
        merkle_proto = bytes.fromhex(self.merkle_root_hex)[::-1]
        return b"".join([
            struct.pack("<I", self.version),
            prev_proto,
            merkle_proto,
            struct.pack("<III", self.timestamp, self.nbits, self.nonce),
        ])

    @classmethod
    def parse(cls, raw: bytes) -> "BlockHeader":
        """从 80 字节协议字节序区块头解析。"""
        if len(raw) != HEADER_SIZE:
            raise FieldRangeError("区块头必须为 80 字节，实际 %d" % len(raw))
        version = struct.unpack_from("<I", raw, 0)[0]
        prev = raw[4:36][::-1].hex()
        merkle = raw[36:68][::-1].hex()
        timestamp, nbits, nonce = struct.unpack_from("<III", raw, 68)
        return cls(version, prev, merkle, timestamp, nbits, nonce)

    # ------------------------------------------------------------------
    # Nonce 修改（PoW 的核心动作）
    # ------------------------------------------------------------------
    def with_nonce(self, nonce: int) -> "BlockHeader":
        """返回仅修改 Nonce 的新区块头（其余 76 字节不变）。"""
        _check_u32(nonce, "nonce")
        return BlockHeader(
            self.version, self.prev_hash_hex, self.merkle_root_hex,
            self.timestamp, self.nbits, nonce,
        )

    # ------------------------------------------------------------------
    # 展示
    # ------------------------------------------------------------------
    def fields_table(self) -> str:
        """返回六个字段的人读对照表（展示序）。"""
        lines = [
            "字段         大小    值（大端展示序）",
            "-----------  ----    " + "-" * 64,
            "Version      4B      %d (0x%08x)" % (self.version, self.version),
            "PrevHash     32B     %s" % self.prev_hash_hex,
            "MerkleRoot   32B     %s" % self.merkle_root_hex,
            "Timestamp    4B      %d" % self.timestamp,
            "nBits        4B      0x%08x" % self.nbits,
            "Nonce        4B      %d (0x%08x)" % (self.nonce, self.nonce),
        ]
        return "\n".join(lines)


def genesis_header(nonce: int = GENESIS_NONCE) -> BlockHeader:
    """构造创世区块头（默认使用真实 Nonce）。"""
    return BlockHeader(
        version=GENESIS_VERSION,
        prev_hash_hex=GENESIS_PREV_HASH_HEX,
        merkle_root_hex=GENESIS_MERKLE_ROOT_HEX,
        timestamp=GENESIS_TIMESTAMP,
        nbits=GENESIS_NBITS,
        nonce=nonce,
    )
