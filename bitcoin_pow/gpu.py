# -*- coding: utf-8 -*-
"""GPU（CUDA）执行封装与 CPU 复核。

GPU 可执行程序契约（cuda/main.cu 编译产物 sha256d_miner）：
    输入参数：
      --header-hex HEX    80 字节区块头（160 个十六进制字符，协议序）
      --target-hex HEX    64 个十六进制字符的 256-bit 目标（search 模式必需）
      --mode MODE         search（默认）| fixed-work
      --start-nonce N     Nonce 起点（必须 < 2^32）
      --seconds S         时长上限（必须 > 0 且有限）
      --max-attempts N    尝试次数上限（必须 >= 1）
      --rounds R          fixed-work 模式轮数（可选，默认按 seconds 跑满）
      --json              以 JSON 输出到 stdout
    退出码：
      0 = 正常执行（含未命中）；2 = 参数错误；3 = CUDA 执行错误
    输出 JSON 关键键：
      status: "RUN_FOUND" | "RUN_NO_HIT"
      mode, device_name, sm_count, cuda_runtime_version, driver_version,
      start_nonce, end_nonce,
      scheduled_attempts,   # 已分配工作量（可能因提前退出而未全部完成）
      completed_hashes,     # 内核实际完成的哈希数（诚实统计）
      elapsed_seconds, hash_rate（= completed / elapsed）,
      found, nonce, hash_hex, reason

GPU 状态枚举（本模块与 CLI 共用）：
    GPU_NOT_RUN     未执行（无二进制/无 GPU），不产出任何数值
    GPU_ERROR       执行出错（参数错误或 CUDA 错误），不产出可信数值
    GPU_RUN_NO_HIT  正常执行完成但未找到合格哈希（attempts/elapsed/rate 保留）
    GPU_RUN_FOUND   正常执行且命中（需 CPU 复核通过后才算成功）

本模块永不编造 GPU 数据。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .block_header import BlockHeader
from .sha256d import block_header_hash, to_display_hex
from .target import compare

# GPU 状态枚举
GPU_NOT_RUN = "GPU_NOT_RUN"
GPU_ERROR = "GPU_ERROR"
GPU_RUN_NO_HIT = "GPU_RUN_NO_HIT"
GPU_RUN_FOUND = "GPU_RUN_FOUND"

EXIT_OK = 0
EXIT_PARAM = 2
EXIT_CUDA = 3


class GpuUnavailableError(RuntimeError):
    """GPU 或 CUDA 可执行程序不可用（GPU_NOT_RUN）。"""


class GpuParameterError(RuntimeError):
    """传给 CUDA 程序的参数非法（GPU_ERROR，对应二进制退出码 2）。"""


class GpuExecutionError(RuntimeError):
    """CUDA 程序执行失败（GPU_ERROR，对应二进制退出码 3）。"""


def gpu_status_from_raw(raw: dict | None) -> str:
    """把 CUDA 输出归一化为 GPU 状态枚举。"""
    if raw is None:
        return GPU_NOT_RUN
    status = raw.get("status")
    if status == "RUN_FOUND":
        return GPU_RUN_FOUND
    if status == "RUN_NO_HIT":
        return GPU_RUN_NO_HIT
    return GPU_ERROR


class GPURunner:
    def __init__(self, binary: str = "cuda/build/sha256d_miner") -> None:
        self.binary = Path(binary)

    def available(self) -> bool:
        return self.binary.exists() and shutil.which(str(self.binary)) is not None

    @staticmethod
    def validate_inputs(seconds: float, max_attempts: int, start_nonce: int) -> None:
        """Python 侧参数预校验（与二进制内校验同规则）。"""
        if not (seconds > 0) or seconds != seconds or seconds == float("inf"):
            raise GpuParameterError("--seconds 必须为正且有限: %r" % seconds)
        if max_attempts < 1:
            raise GpuParameterError("--max-attempts 必须 >= 1: %r" % max_attempts)
        if not 0 <= start_nonce < (1 << 32):
            raise GpuParameterError("--start-nonce 必须在 [0, 2^32): %r" % start_nonce)

    def mine(
        self,
        header: BlockHeader,
        target: int | None = None,
        start_nonce: int = 0,
        seconds: float = 30.0,
        max_attempts: int = 1 << 40,
        mode: str = "search",
        rounds: int | None = None,
    ) -> dict:
        """调用 CUDA 程序，按退出码分类结果。

        返回 dict（未复核原始数据）。正常执行（含未命中）直接返回；
        参数错误抛 GpuParameterError；CUDA 错误抛 GpuExecutionError；
        二进制缺失抛 GpuUnavailableError。
        """
        if not self.available():
            raise GpuUnavailableError("找不到 CUDA 可执行程序 %s" % self.binary)
        self.validate_inputs(seconds, max_attempts, start_nonce)
        if mode not in ("search", "fixed-work"):
            raise GpuParameterError("mode 必须为 search 或 fixed-work: %r" % mode)
        if mode == "search" and target is None:
            raise GpuParameterError("search 模式需要 target")

        cmd = [
            str(self.binary),
            "--header-hex", header.serialize().hex(),
            "--mode", mode,
            "--start-nonce", str(start_nonce),
            "--seconds", str(seconds),
            "--max-attempts", str(max_attempts),
            "--json",
        ]
        if mode == "search":
            cmd += ["--target-hex", "%064x" % target]
        if mode == "fixed-work" and rounds is not None:
            if rounds < 1:
                raise GpuParameterError("rounds 必须 >= 1: %r" % rounds)
            cmd += ["--rounds", str(rounds)]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=seconds + 120,
            )
        except subprocess.TimeoutExpired as exc:
            raise GpuExecutionError("CUDA 程序超时: %s" % exc) from exc
        except OSError as exc:
            raise GpuExecutionError("CUDA 程序启动失败: %s" % exc) from exc

        if proc.returncode == EXIT_PARAM:
            raise GpuParameterError(
                "CUDA 程序拒绝参数（exit 2）: %s" % proc.stderr.strip())
        if proc.returncode == EXIT_CUDA:
            raise GpuExecutionError(
                "CUDA 执行错误（exit 3）: %s" % proc.stderr.strip())
        if proc.returncode != EXIT_OK:
            raise GpuExecutionError(
                "CUDA 程序异常退出（exit %d）: %s" % (proc.returncode,
                                                     proc.stderr.strip()))
        try:
            raw = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise GpuExecutionError(
                "CUDA 程序输出不是合法 JSON: %r" % proc.stdout) from exc
        if raw.get("status") not in ("RUN_FOUND", "RUN_NO_HIT"):
            raise GpuExecutionError("CUDA 程序状态异常: %r" % raw.get("status"))
        return raw


def recheck_gpu_result(header: BlockHeader, target: int, raw: dict) -> bool:
    """CPU 独立复核 GPU 结果（门禁）。

    - 未命中（RUN_NO_HIT）：无命中声明需要验证，直接通过。
    - 命中（RUN_FOUND）：CPU 重建区块头、计算 SHA256d，
      比对哈希逐字节一致且 H <= T。
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
