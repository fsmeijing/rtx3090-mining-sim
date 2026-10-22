# -*- coding: utf-8 -*-
"""算力统计与报告。

数据来源标签（必须逐数值标注，禁止混淆）：
  MEASURED      真实测量值：本次实际执行得到
  THEORETICAL   理论推算值：按公式推算（附推算依据），只报告有可靠模型的量
  TEACHING_SIM  教学模拟值：与真实硬件无关的教学参数

诚实统计契约：
  - scheduled_attempts：已分配给 GPU 的工作量（可能因命中提前退出而未完成）
  - completed_hashes：内核实际完成的哈希数（atomicAdd 累计）
  - hash_rate：completed_hashes / elapsed_seconds，绝不使用 scheduled 冒充
  - 固定工作量 benchmark：无命中判定、无提前退出、预设 Nonce 范围、
    32-bit 边界截断如实报告、多次运行统计吞吐量

无 GPU 环境时输出 GPU_STATUS: NOT_RUN，绝不伪造实测数据。
"""

from __future__ import annotations

import shutil
import statistics
import subprocess
from datetime import datetime, timezone

from .block_header import genesis_header
from .genesis import search_nonce
from .gpu import (
    GPU_ERROR,
    GPU_NOT_RUN,
    GPU_RUN_FOUND,
    GPU_RUN_NO_HIT,
    GPURunner,
    GpuExecutionError,
    GpuParameterError,
    GpuUnavailableError,
    recheck_gpu_result,
)
from .target import MODE_EASY, GENESIS_TARGET, mode_target, target_to_hex


def _nvidia_smi_info() -> dict:
    """读取 GPU 型号 / 驱动版本（真实环境探测，失败则返回空）。"""
    if shutil.which("nvidia-smi") is None:
        return {}
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip().splitlines()
        if not out:
            return {}
        name, driver = [x.strip() for x in out[0].split(",")]
        return {"gpu_name": name, "driver_version": driver}
    except (subprocess.SubprocessError, OSError, ValueError):
        return {}


def _theoretical_breakdown(sm_count: int | None) -> dict:
    """理论吞吐量分层说明。

    只报告有可靠模型支撑的量：
      1. 32-bit 整数操作吞吐量：SM×128核×每周期1次INT32×boost频率 —— 确定的
         芯片规格推算（THEORETICAL）。
      2. SHA-256 压缩吞吐量：一个压缩函数 ≈ 64 轮 × 每轮约 10 次 32-bit
         运算（含消息扩展摊销）≈ 700+ 次整数运算，可给出**绝对上界量级**，
         但真实利用率取决于内核实现（THEORETICAL，注明为上界）。
      3. SHA-256d 哈希吞吐量 = 2 次压缩/哈希：本仓库**不建立**可靠模型
         （每压缩真实运算数、寄存器压力、调度开销均无法从规格推算），
         因此 theoretical_sha256d_hash_rate 报告 null，唯一可信数字是
         固定工作量 benchmark 的 MEASURED 值。
    """
    if not sm_count:
        return {}
    int_ops_per_s = sm_count * 128 * 1.70e9   # 32-bit INT32 ops/s（每核每周期1次）
    compress_ops = 750                        # 每次压缩的整数运算数（粗估）
    return {
        "integer_ops_throughput": {
            "value": int_ops_per_s,
            "source": "THEORETICAL",
            "unit": "32-bit integer ops/s",
            "formula": "SM数 × 128 CUDA核/SM × 1.70GHz × 1 INT32 op/cycle",
        },
        "sha256_compression_throughput": {
            "value": int_ops_per_s / compress_ops,
            "source": "THEORETICAL",
            "unit": "SHA-256 compressions/s（绝对上界量级）",
            "formula": "integer_ops / ~750 ops per compression（假设每周期每核1次整数运算，忽略一切开销）",
            "caveat": "仅为不可达的绝对上界，不构成对实测值的预测",
        },
        "sha256d_hash_rate": {
            "value": None,
            "source": "THEORETICAL",
            "note": "无可靠理论模型（压缩内部依赖链/寄存器压力/调度开销不可从规格推算），不报告理论 SHA-256d H/s；唯一可信数字是 benchmark 的 MEASURED 值",
        },
    }


def run_benchmark(
    mode: str = MODE_EASY,
    gpu: bool = False,
    binary: str = "cuda/build/sha256d_miner",
    seconds: float = 10.0,
    max_attempts: int = 1 << 40,
    seed: int | None = None,
    fixed_runs: int = 3,
    fixed_rounds: int = 20,
) -> dict:
    """运行 benchmark 并返回带来源标签的报告字典。

    GPU 路径：
      1. correctness_check：search 模式 easy 目标快速命中 + CPU 复核，
         证明内核计算的是真实 SHA256d；
      2. fixed_workload：fixed-work 模式重复 fixed_runs 次（每次 fixed_rounds
         轮、预设 Nonce 起点、无提前退出），逐次统计 completed/elapsed，
         汇总 min/median/max 吞吐量。
    """
    header = genesis_header()
    target = mode_target(mode)
    base = {
        "schema": "rtx3090-mining-sim/benchmark-v2",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": seed,
        "mode": mode,
        "target_hex": target_to_hex(target),
        "target_source": "派生自创世 nBits=0x1d00ffff（确定值）",
        "target_nbits": "0x%08x" % header.nbits,
        "hash_function": "SHA256d（SHA256(SHA256(80B header))）",
        "offline": True,
        "statistics_contract": {
            "scheduled_attempts": "有效分配的候选 Nonce 数量（精确窗口，<= max_attempts）",
            "completed_hashes": "内核实际完成哈希数（atomicAdd，<= scheduled_attempts）",
            "hash_rate": "completed_hashes / elapsed_seconds（MEASURED）",
        },
    }

    if not gpu:
        # CPU 参考测速：固定工作量（不依赖 GPU），仍然真实测量
        t0 = __import__("time").perf_counter()
        res = search_nonce(header, target, start_nonce=0, max_attempts=200000)
        elapsed = __import__("time").perf_counter() - t0
        base.update({
            "gpu_status": GPU_NOT_RUN,
            "gpu_status_note": "未指定 --gpu；GPU_STATUS=NOT_RUN 时不含任何 GPU 数值",
            "cpu_reference": {
                "source": "MEASURED",
                "completed_hashes": res.attempts,
                "elapsed_seconds": round(elapsed, 4),
                "hash_rate": round(res.attempts / elapsed, 1) if elapsed > 0 else None,
                "note": "Python hashlib 单线程 CPU 参考值，仅供对照",
            },
        })
        return base

    runner = GPURunner(binary)
    if not runner.available():
        base.update({
            "gpu_status": GPU_NOT_RUN,
            "gpu_status_note": "CUDA 可执行程序不存在：%s（请先 scripts/build_cuda.sh）" % binary,
            "gpu": None,
        })
        return base

    smi = _nvidia_smi_info()

    # ---- 1. 正确性检验：search easy 命中 + CPU 复核 ----
    try:
        check_raw = runner.mine(
            header, mode_target(MODE_EASY), start_nonce=0,
            seconds=10.0, max_attempts=1 << 32, mode="search",
        )
    except (GpuParameterError, GpuExecutionError) as exc:
        base.update({
            "gpu_status": GPU_ERROR,
            "gpu_status_note": str(exc),
            "gpu": None,
        })
        return base
    check_ok = recheck_gpu_result(header, mode_target(MODE_EASY), check_raw)

    # ---- 2. 固定工作量吞吐统计（无命中提前退出，多次运行） ----
    # max-attempts 语义：**每次运行的预算**（各次运行独立享有，
    # 非所有运行共享的总额），与 CLI/JSON/OpenSpec/文档保持一致。
    runs = []
    status = GPU_RUN_NO_HIT
    error_note = None
    for i in range(max(1, fixed_runs)):
        try:
            raw = runner.mine(
                header, None, start_nonce=0,
                seconds=seconds, max_attempts=1 << 40,
                mode="fixed-work", rounds=fixed_rounds,
            )
        except (GpuParameterError, GpuExecutionError) as exc:
            status = GPU_ERROR
            error_note = str(exc)
            break
        completed = raw["completed_hashes"]
        elapsed = raw["elapsed_seconds"]
        runs.append({
            "run": i + 1,
            "start_nonce": raw["start_nonce"],
            "end_nonce": raw["end_nonce"],
            "max_attempts_budget_per_run": raw["max_attempts_budget"],
            "scheduled_attempts": raw["scheduled_attempts"],
            "completed_hashes": completed,
            "rounds": raw["rounds"],
            "reason": raw["reason"],
            "elapsed_seconds": round(elapsed, 6),
            "hash_rate": round(completed / elapsed, 1) if elapsed > 0 else None,
            "source": "MEASURED",
        })
        status = GPU_RUN_NO_HIT

    rates = [r["hash_rate"] for r in runs if r["hash_rate"]]
    completed_total = sum(r["completed_hashes"] for r in runs)
    elapsed_total = sum(r["elapsed_seconds"] for r in runs)

    if status == GPU_ERROR:
        base.update({"gpu_status": GPU_ERROR, "gpu_status_note": error_note,
                     "gpu": {"correctness_check": check_ok}})
        return base

    base.update({
        "gpu_status": status,
        "gpu_status_note": "固定工作量模式正常执行、无命中属于预期（found=false），GPU_STATUS=RUN",
        "gpu": {
            "correctness_check": {
                "value": "PASS" if check_ok else "FAIL",
                "source": "MEASURED",
                "method": "search 模式 easy 目标命中 Nonce 后，CPU 用 hashlib 重建区块头复算比对",
                "hit_nonce": check_raw.get("nonce"),
                "hit_hash_hex": check_raw.get("hash_hex"),
            },
            "device_name": {"value": check_raw.get("device_name"), "source": "MEASURED"},
            "sm_count": {"value": check_raw.get("sm_count"), "source": "MEASURED"},
            "cuda_runtime_version": {"value": check_raw.get("cuda_runtime_version"), "source": "MEASURED"},
            "driver_version": {"value": check_raw.get("driver_version") or smi.get("driver_version"),
                                "source": "MEASURED"},
            "fixed_workload": {
                "description": "fixed-work 模式：无 H<=T 判定、无命中提前退出、Nonce 范围由预算与 32-bit 上界精确截断、受 max-attempts/rounds/seconds 三限约束（优先记录最早触发者）",
                "max_attempts_budget": {
                    "per_run": max_attempts,
                    "semantics": "每次运行的预算（fixed_runs 次运行各享 max_attempts，非共享总额）；本次运行各次实际 reason 见 runs[].reason",
                    "source": "USER_INPUT",
                },
                "runs": fixed_runs,
                "rounds_per_run": fixed_rounds,
                "results": runs,
                "total_completed_hashes": {"value": completed_total, "source": "MEASURED"},
                "total_elapsed_seconds": {"value": round(elapsed_total, 6), "source": "MEASURED"},
                "hash_rate": {
                    "unit": "H/s（completed/elapsed，MEASURED）",
                    "min": min(rates) if rates else None,
                    "median": statistics.median(rates) if rates else None,
                    "max": max(rates) if rates else None,
                },
                "hash_rate_mhs": {
                    "median": (statistics.median(rates) / 1e6) if rates else None,
                    "source": "MEASURED",
                },
                "hash_rate_ghs": {
                    "median": (statistics.median(rates) / 1e9) if rates else None,
                    "source": "MEASURED",
                },
            },
            "theoretical_breakdown": _theoretical_breakdown(check_raw.get("sm_count")),
            "cpu_recheck": {"value": "PASS" if check_ok else "FAIL", "source": "MEASURED"},
        },
    })
    return base
