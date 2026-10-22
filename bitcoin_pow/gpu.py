# -*- coding: utf-8 -*-
"""GPU（CUDA）执行封装与 CPU 复核。

GPU 可执行程序契约（cuda/main.cu 编译产物 sha256d_miner）：
    输入参数：
      --header-hex HEX    80 字节区块头（160 个十六进制字符，协议序）
      --target-hex HEX    64 个十六进制字符的 256-bit 目标
      --start-nonce N     Nonce 起点
      --seconds S         时长上限
      --max-attempts N    尝试次数上限
      --json              以 JSON 输出到 stdout
    输出 JSON 键：
      device_name, sm_count, cuda_runtime_version, driver_version,
      start_nonce, end_nonce, attempts, elapsed_seconds, hash_rate,
      found, nonce, hash_hex, reason

本模块永不编造 GPU 数据：二进制不可用/执行失败时抛出 GpuUnavailableError，
由 CLI 输出 GPU_STATUS: NOT_RUN。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .block_header import BlockHeader
from .sha256d import block_header_hash, to_display_hex
from .target import compare


class GpuUnavailableError(RuntimeError):
    """GPU 或 CUDA 可执行程序不可用。"""


class GPURunner:
    def __init__(self, binary: str = "cuda/build/sha256d_miner") -> None:
        self.binary = Path(binary)

    def available(self) -> bool:
        return self.binary.exists() and shutil.which(str(self.binary)) is not None

    def mine(
        self,
        header: BlockHeader,
        target: int,
        start_nonce: int = 0,
        seconds: float = 30.0,
        max_attempts: int = 1 << 40,
    ) -> dict:
        """调用 CUDA 程序执行 Nonce 搜索，返回其 JSON 输出（未复核原始数据）。"""
        if not self.available():
            raise GpuUnavailableError("找不到 CUDA 可执行程序 %s" % self.binary)
        cmd = [
            str(self.binary),
            "--header-hex", header.serialize().hex(),
            "--target-hex", "%064x" % target,
            "--start-nonce", str(start_nonce),
            "--seconds", str(seconds),
            "--max-attempts", str(max_attempts),
            "--json",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=seconds + 120,
                check=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise GpuUnavailableError("CUDA 程序执行失败: %s" % exc) from exc
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise GpuUnavailableError("CUDA 程序输出不是合法 JSON: %r" % proc.stdout) from exc


def recheck_gpu_result(header: BlockHeader, target: int, raw: dict) -> bool:
    """CPU 独立复核 GPU 结果（门禁）。

    - 未命中：直接通过（无声明需要验证）。
    - 命中：CPU 重建区块头、计算 SHA256d，比对哈希逐字节一致且 H <= T。
    """
    if not raw.get("found"):
        return True
    nonce = int(raw["nonce"])
    claimed_hex = str(raw.get("hash_hex", "")).lower()
    digest = block_header_hash(header.with_nonce(nonce).serialize())
    expected_hex = to_display_hex(digest)
    if expected_hex != claimed_hex:
        return False
    return compare(digest, target)


def recheck_result_strict(header: BlockHeader, target: int, raw: dict) -> str:
    """带结论字符串的复核（供报告使用）：PASS / FAIL。"""
    return "PASS" if recheck_gpu_result(header, target, raw) else "FAIL"
