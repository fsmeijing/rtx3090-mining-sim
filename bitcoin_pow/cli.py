# -*- coding: utf-8 -*-
"""统一命令行入口。

示例：
    python3 -m bitcoin_pow --verify
    python3 -m bitcoin_pow --mode easy --max-attempts 100000
    python3 -m bitcoin_pow --mode easy --gpu --binary cuda/build/sha256d_miner
    python3 -m bitcoin_pow --benchmark --mode medium --gpu --seconds 10
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import __version__
from .benchmark import run_benchmark
from .genesis import search_nonce, verify_genesis
from .gpu import GPURunner, GpuUnavailableError
from .target import (
    MODE_EASY,
    MODE_GENESIS,
    MODE_MEDIUM,
    leading_zero_bits,
    mode_target,
    nbits_to_target,
    target_to_hex,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bitcoin_pow",
        description="比特币 SHA-256d 工作量证明教学实验（完全离线）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--version", action="version", version="bitcoin_pow %s" % __version__)
    p.add_argument("--verify", action="store_true",
                   help="复算创世区块并比对已知哈希")
    p.add_argument("--mode", choices=(MODE_EASY, MODE_MEDIUM, MODE_GENESIS),
                   default=MODE_EASY, help="教学难度模式")
    p.add_argument("--benchmark", action="store_true",
                   help="固定工作量测速并输出算力报告")
    p.add_argument("--seconds", type=float, default=30.0,
                   help="运行时长上限（秒）")
    p.add_argument("--max-attempts", type=int, default=1 << 32,
                   help="累计尝试次数上限")
    p.add_argument("--start-nonce", type=int, default=0,
                   help="Nonce 搜索起点")
    p.add_argument("--gpu", action="store_true",
                   help="使用 GPU（CUDA 可执行程序）；不可用时如实报告 NOT_RUN")
    p.add_argument("--binary", default="cuda/build/sha256d_miner",
                   help="CUDA 可执行程序路径")
    p.add_argument("--json", metavar="PATH", help="将结果报告导出为 JSON")
    p.add_argument("--seed", type=int, default=None,
                   help="确定性参数（当前用于固定报告元数据）")
    return p


def print_target_info(mode: str) -> int:
    target = mode_target(mode)
    print("难度模式      : %s" % mode)
    print("目标 T        : %s" % target_to_hex(target))
    print("前导零比特    : %d bit（完整 256-bit 整数比较 H <= T）" % leading_zero_bits(target))
    return target


def cmd_verify() -> int:
    result = verify_genesis()
    print("=" * 70)
    print("创世区块六字段（80 字节区块头，协议小端序）")
    print("=" * 70)
    print(result.header.fields_table())
    print("-" * 70)
    print(result.summary())
    print("=" * 70)
    return 0 if result.match else 1


def run_gpu_mine(args, header, target) -> dict:
    runner = GPURunner(args.binary)
    return runner.mine(
        header, target,
        start_nonce=args.start_nonce,
        seconds=args.seconds,
        max_attempts=args.max_attempts,
    )


def cmd_mine(args) -> int:
    from .block_header import genesis_header
    from .gpu import (
        GPU_ERROR,
        GPU_NOT_RUN,
        GPU_RUN_FOUND,
        GPU_RUN_NO_HIT,
        GpuExecutionError,
        GpuParameterError,
    )

    if args.seconds <= 0 or args.max_attempts < 1 or not (
            0 <= args.start_nonce < (1 << 32)):
        print("PARAM_ERROR：--seconds 须为正、--max-attempts 须 >= 1、"
              "--start-nonce 须在 [0, 2^32)")
        return 2

    print("=" * 70)
    print("比特币 SHA-256d 工作量证明实验（完全离线教学模拟）")
    print("=" * 70)
    target = print_target_info(args.mode)
    header = genesis_header()   # 实验固定使用创世区块头（改 Nonce 之外的字段无意义）
    print("区块头        : 创世区块（详见 --verify）")
    print("-" * 70)

    gpu_status = GPU_NOT_RUN
    report = {"command": "mine", "mode": args.mode}

    if args.gpu:
        try:
            raw = run_gpu_mine(args, header, target)
        except GpuUnavailableError as exc:
            gpu_status = GPU_NOT_RUN
            print("GPU_STATUS    : NOT_RUN（原因：%s）" % exc)
            print("说明          : 未产生任何 GPU 计算结果，以上不包含实测数据。")
            report.update({"gpu_status": gpu_status})
            _finish_mine(args, report)
            return 0
        except (GpuParameterError, GpuExecutionError) as exc:
            gpu_status = GPU_ERROR
            print("GPU_STATUS    : ERROR（%s）" % exc)
            print("说明          : 执行失败，不存在可信的 GPU 数值，绝不编造。")
            report.update({"gpu_status": gpu_status})
            _finish_mine(args, report)
            return 3

        from .gpu import gpu_status_from_raw, recheck_gpu_result

        gpu_status = gpu_status_from_raw(raw)
        if gpu_status == GPU_RUN_FOUND:
            ok = recheck_gpu_result(header, target, raw)
            print("CPU 复核      : %s" % ("PASS" if ok else "FAIL"))
            if not ok:
                report.update({"gpu_status": gpu_status, "cpu_recheck": "FAIL"})
                _finish_mine(args, report)
                return 2
            print("GPU 状态      : RUN_FOUND")
            print("命中 Nonce    : %d" % raw["nonce"])
            print("成功哈希 H    : %s" % raw["hash_hex"])
        else:   # GPU_RUN_NO_HIT：正常执行但未命中，保留全部统计
            print("GPU 状态      : RUN_NO_HIT（正常执行，未找到合格哈希）")
        print("累计分配      : %d（scheduled_attempts，MEASURED）" % raw["scheduled_attempts"])
        print("实际完成      : %d（completed_hashes，MEASURED）" % raw["completed_hashes"])
        print("用时          : %.3f s（MEASURED）" % raw["elapsed_seconds"])
        print("GPU 算力      : %s H/s（completed/elapsed，MEASURED）"
              % format(int(raw["hash_rate"]), ","))
        if gpu_status == GPU_RUN_NO_HIT:
            print("结果          : found=false（如实报告，不伪造成功）")
        report.update({
            "gpu_status": gpu_status,
            "gpu": raw,
            "cpu_recheck": ("PASS" if gpu_status == GPU_RUN_FOUND
                            and recheck_gpu_result(header, target, raw)
                            else "N/A" if gpu_status == GPU_RUN_NO_HIT else "FAIL"),
        })
    else:
        t0 = time.perf_counter()
        res = search_nonce(
            header, target,
            start_nonce=args.start_nonce,
            max_attempts=args.max_attempts,
        )
        elapsed = time.perf_counter() - t0
        rate = res.attempts / elapsed if elapsed > 0 else 0.0
        print("搜索方式      : CPU 参考实现（hashlib）")
        print("累计尝试      : %d（MEASURED，completed）" % res.attempts)
        print("用时          : %.3f s（MEASURED）" % elapsed)
        print("CPU 算力      : %.0f H/s（MEASURED）" % rate)
        if res.found:
            print("命中 Nonce    : %d" % res.nonce)
            print("成功哈希 H    : %s" % res.hash_hex)
            print("结论          : H <= T 成立（完整 256-bit 整数比较）")
        else:
            print("结果          : %s（%d 次尝试内未找到解）" % (res.reason, res.attempts))
        report.update({
            "gpu_status": GPU_NOT_RUN,
            "attempts": res.attempts, "elapsed_seconds": elapsed,
            "cpu_hash_rate": rate, "found": res.found,
            "nonce": res.nonce, "hash_hex": res.hash_hex,
            "reason": res.reason,
        })

    _finish_mine(args, report)
    return 0


def _finish_mine(args, report: dict) -> None:
    if args.json:
        import pathlib

        pathlib.Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("报告已导出    : %s" % args.json)
    print("=" * 70)


def cmd_benchmark(args) -> int:
    report = run_benchmark(
        mode=args.mode,
        gpu=args.gpu,
        binary=args.binary,
        seconds=args.seconds,
        max_attempts=args.max_attempts,
        seed=args.seed,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json:
        import pathlib

        pathlib.Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("报告已导出    : %s" % args.json)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.verify:
        return cmd_verify()
    if args.benchmark:
        return cmd_benchmark(args)
    return cmd_mine(args)


if __name__ == "__main__":
    sys.exit(main())
