# -*- coding: utf-8 -*-
"""算力统计与报告。

数据来源标签（必须逐数值标注，禁止混淆）：
  MEASURED      真实测量值：本次实际执行得到
  THEORETICAL   理论推算值：按公式推算（附推算依据）
  TEACHING_SIM  教学模拟值：与真实硬件无关的教学参数
无 GPU 环境时输出 GPU_STATUS: NOT_RUN，绝不伪造实测数据。
"""

from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime, timezone

from .block_header import genesis_header
from .genesis import search_nonce
from .gpu import GPURunner, GpuUnavailableError, recheck_gpu_result
from .target import MODE_EASY, mode_target, nbits_to_target, target_to_hex


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


def run_benchmark(
    mode: str = MODE_EASY,
    gpu: bool = False,
    binary: str = "cuda/build/sha256d_miner",
    seconds: float = 10.0,
    max_attempts: int = 1 << 40,
    seed: int | None = None,
) -> dict:
    """运行 benchmark 并返回带来源标签的报告字典。"""
    header = genesis_header()
    target = mode_target(mode)
    base = {
        "schema": "rtx3090-mining-sim/benchmark-v1",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": seed,
        "mode": mode,
        "target_hex": target_to_hex(target),
        "target_source": "MEASURED_NA / 派生自创世 nBits=0x1d00ffff（确定值）",
        "target_nbits": "0x%08x" % header.nbits,
        "hash_function": "SHA256d（SHA256(SHA256(80B header))）",
        "offline": True,
    }

    if not gpu:
        # CPU 参考测速：固定工作量（不依赖 GPU），仍然真实测量
        t0 = time.perf_counter()
        res = search_nonce(header, target, start_nonce=0, max_attempts=200000)
        elapsed = time.perf_counter() - t0
        base.update({
            "gpu_status": "NOT_RUN（未指定 --gpu）",
            "cpu_reference": {
                "source": "MEASURED",
                "attempts": res.attempts,
                "elapsed_seconds": round(elapsed, 4),
                "hash_rate": round(res.attempts / elapsed, 1) if elapsed > 0 else None,
                "note": "Python hashlib 单线程 CPU 参考值，仅供对照",
            },
        })
        return base

    runner = GPURunner(binary)
    if not runner.available():
        base.update({
            "gpu_status": "NOT_RUN（CUDA 可执行程序不存在：%s；请先 scripts/build_cuda.sh）" % binary,
            "gpu": None,
        })
        return base

    try:
        raw = runner.mine(
            header, target, start_nonce=0,
            seconds=seconds, max_attempts=max_attempts,
        )
    except GpuUnavailableError as exc:
        base.update({"gpu_status": "NOT_RUN（%s）" % exc, "gpu": None})
        return base

    smi = _nvidia_smi_info()
    ok = recheck_gpu_result(header, target, raw)
    theoretical = _theoretical_hash_rate(raw.get("sm_count"))
    base.update({
        "gpu_status": "RUN",
        "gpu": {
            "device_name": {"value": raw.get("device_name"), "source": "MEASURED"},
            "sm_count": {"value": raw.get("sm_count"), "source": "MEASURED"},
            "cuda_runtime_version": {"value": raw.get("cuda_runtime_version"), "source": "MEASURED"},
            "driver_version": {"value": raw.get("driver_version") or smi.get("driver_version"),
                                "source": "MEASURED"},
            "nonce_range": {"value": [raw.get("start_nonce"), raw.get("end_nonce")],
                            "source": "MEASURED"},
            "attempts": {"value": raw.get("attempts"), "source": "MEASURED"},
            "elapsed_seconds": {"value": raw.get("elapsed_seconds"), "source": "MEASURED"},
            "hash_rate": {"value": raw.get("hash_rate"), "source": "MEASURED", "unit": "H/s"},
            "hash_rate_mhs": {"value": (raw.get("hash_rate") or 0) / 1e6,
                              "source": "MEASURED", "unit": "MH/s"},
            "hash_rate_ghs": {"value": (raw.get("hash_rate") or 0) / 1e9,
                              "source": "MEASURED", "unit": "GH/s"},
            "theoretical_hash_rate": theoretical,
            "found": raw.get("found"),
            "hit_nonce": raw.get("nonce"),
            "hit_hash_hex": raw.get("hash_hex"),
            "target_hex": target_to_hex(target),
            "cpu_recheck": {"value": "PASS" if ok else "FAIL", "source": "MEASURED"},
            "cpu_recheck_note": "CPU 用 Python hashlib 重建区块头并复算 SHA256d 后比对",
        },
    })
    return base


def _theoretical_hash_rate(sm_count: int | None) -> dict | None:
    """理论推算：RTX 3090 每SM 128 CUDA核 @ ~1.70 GHz，每核每周期约 1 次整数蝶形运算。

    该推算仅为数量级参考，真实 SHA256d 算力依赖内核实现，必须以 MEASURED 为准。
    """
    if not sm_count:
        return None
    cuda_cores = sm_count * 128
    boost_ghz = 1.70
    est = cuda_cores * boost_ghz * 1e9
    return {
        "value": est,
        "source": "THEORETICAL",
        "unit": "H/s（上界量级）",
        "formula": "SM数 × 128 CUDA核/SM × 1.70GHz × 1 op/cycle（未考虑真实内核效率）",
    }
