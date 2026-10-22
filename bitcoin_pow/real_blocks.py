# -*- coding: utf-8 -*-
"""高度 0–19 真实区块测试向量加载器（完全离线，只读 data/ JSON）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "blocks_0_19.json"


@dataclass
class RealBlock:
    """一条真实区块测试向量（来自比特币主网）。"""

    height: int
    version: int
    prev_hash_hex: str       # 大端展示序
    merkle_root_hex: str     # 大端展示序
    timestamp: int
    nbits: int
    nonce: int
    hash_hex: str            # 大端展示序（区块浏览器方向）
    raw_header_hex: str      # 80 字节协议序原始头（数据源权威依据）


def load_real_blocks() -> list[RealBlock]:
    """加载内置的高度 0–19 真实区块向量。"""
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            "缺少测试向量数据文件: %s（请运行 scripts/fetch_real_blocks.py 生成）" % DATA_PATH
        )
    with open(DATA_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return [RealBlock(**item) for item in raw["blocks"]]


def source_metadata() -> dict:
    """数据来源元信息。"""
    with open(DATA_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return raw["meta"]
