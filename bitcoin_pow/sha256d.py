# -*- coding: utf-8 -*-
"""双重 SHA-256（SHA256d）CPU 参考实现。

比特币区块头哈希：H = SHA256( SHA256( 80字节区块头 ) )
结果为 32 字节（256 bit）。展示时按区块浏览器习惯做字节倒序。
"""

from __future__ import annotations

import hashlib

DIGEST_SIZE = 32


def sha256(data: bytes) -> bytes:
    """单次 SHA-256，返回 32 字节摘要。"""
    return hashlib.sha256(data).digest()


def sha256d(data: bytes) -> bytes:
    """双重 SHA-256：SHA256(SHA256(data))，返回 32 字节协议序摘要。"""
    return sha256(sha256(data))


def block_header_hash(header80: bytes) -> bytes:
    """区块头 SHA256d 哈希（32 字节，协议序）。"""
    if len(header80) != 80:
        raise ValueError("区块头必须为 80 字节，实际 %d" % len(header80))
    return sha256d(header80)


def to_display_hex(digest: bytes) -> str:
    """协议序 32 字节 -> 大端展示十六进制（区块浏览器方向）。"""
    return digest[::-1].hex()


def from_display_hex(hex_str: str) -> bytes:
    """大端展示十六进制 -> 协议序 32 字节。"""
    return bytes.fromhex(hex_str)[::-1]
