# -*- coding: utf-8 -*-
"""生成高度 0–19 真实区块测试向量。

数据来源：blockstream.info 公开 API（GET /api/block-height/<h> 与 /api/block/<hash>/header）。
本脚本仅在"开发者手动更新数据"时联网使用；模拟器本体完全离线。

用法：
    python3 scripts/fetch_real_blocks.py --fetch          # 从 API 抓取并生成
    python3 scripts/fetch_real_blocks.py --from-raw-file FILE
        # FILE 每行: "<height> <block_hash> <80字节raw头hex>"

输出：bitcoin_pow/data/blocks_0_19.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from bitcoin_pow.block_header import BlockHeader  # noqa: E402

API = "https://blockstream.info/api"


def decode_raw_header(raw: bytes, height: int, api_hash: str | None) -> dict:
    header = BlockHeader.parse(raw)
    our_hash = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[::-1].hex()
    if api_hash is not None and our_hash != api_hash:
        raise SystemExit("高度 %d: 本地复算哈希与 API 不一致" % height)
    return {
        "height": height,
        "version": header.version,
        "prev_hash_hex": header.prev_hash_hex,
        "merkle_root_hex": header.merkle_root_hex,
        "timestamp": header.timestamp,
        "nbits": header.nbits,
        "nonce": header.nonce,
        "hash_hex": our_hash,
        "raw_header_hex": raw.hex(),
    }


def fetch_blocks(heights: range) -> list[dict]:
    import urllib.request  # 仅本脚本使用（数据采集工具），模拟器本体不联网

    blocks = []
    for h in heights:
        with urllib.request.urlopen("%s/block-height/%d" % (API, h), timeout=30) as r:
            api_hash = r.read().decode().strip()
        with urllib.request.urlopen("%s/block/%s/header" % (API, api_hash), timeout=30) as r:
            raw = bytes.fromhex(r.read().decode().strip())
        if len(raw) != 80:
            raise SystemExit("高度 %d: API 返回头不是 80 字节" % h)
        blocks.append(decode_raw_header(raw, h, api_hash))
        print("已抓取高度 %d: %s" % (h, blocks[-1]["hash_hex"]))
    return blocks


def from_raw_file(path: str) -> list[dict]:
    blocks = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        h_str, api_hash, raw_hex = line.split()
        raw = bytes.fromhex(raw_hex)
        if len(raw) != 80:
            raise SystemExit("高度 %s: 原始头不是 80 字节" % h_str)
        blocks.append(decode_raw_header(raw, int(h_str), api_hash))
    return blocks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--fetch", action="store_true", help="从 blockstream API 抓取高度 0-19")
    g.add_argument("--from-raw-file", metavar="FILE", help="从已抓取的原始头文件生成")
    args = ap.parse_args()

    blocks = fetch_blocks(range(0, 20)) if args.fetch else from_raw_file(args.from_raw_file)
    if [b["height"] for b in blocks] != list(range(20)):
        raise SystemExit("高度序列不是 0..19")

    doc = {
        "meta": {
            "description": "比特币主网高度 0-19 真实区块头测试向量（80 字节 raw 头 + 解码字段）",
            "source": "blockstream.info API（/api/block-height/<h>, /api/block/<hash>/header）",
            "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "count": len(blocks),
            "offline_note": "模拟器本体完全离线；本数据文件为静态测试向量。",
        },
        "blocks": blocks,
    }
    out = REPO / "bitcoin_pow" / "data" / "blocks_0_19.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("已生成: %s（%d 个区块）" % (out, len(blocks)))


if __name__ == "__main__":
    main()
