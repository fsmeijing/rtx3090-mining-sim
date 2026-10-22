# -*- coding: utf-8 -*-
"""计算预算边界测试（真实 RTX 3090 实测）。

验证 CUDA 端精确预算契约：
    completed_hashes <= scheduled_attempts <= max_attempts
    fixed-work 无命中时 scheduled == completed == 预算（精确到个位数）

无 GPU / 无 CUDA 可执行程序时显式 skipTest（CI 标记 SKIP，绝不伪造）。
运行前置：scripts/build_cuda.sh 已产出 cuda/build/sha256d_miner 且本机有 GPU。
"""

import json
import os
import unittest

from bitcoin_pow.block_header import genesis_header
from bitcoin_pow.gpu import (
    GpuParameterError,
    GPURunner,
)

BINARY = os.environ.get("SHA256D_MINER", "cuda/build/sha256d_miner")

# 不可能命中的目标（全零 < 任何哈希）
TARGET_NEVER_HIT = "0" * 64
# 必然命中的目标（最大值 >= 任何哈希）
TARGET_ALWAYS_HIT = "f" * 64


def _invariant_ok(raw, max_attempts):
    """输出字段内部一致性检查（所有预算用例共用）。"""
    problems = []
    if raw["completed_hashes"] > raw["scheduled_attempts"]:
        problems.append("completed > scheduled")
    if raw["scheduled_attempts"] > max_attempts:
        problems.append("scheduled > max_attempts")
    span = raw["end_nonce"] - raw["start_nonce"]
    if span != raw["scheduled_attempts"]:
        problems.append("end-start(%d) != scheduled(%d)" % (span, raw["scheduled_attempts"]))
    if raw["max_attempts_budget"] != max_attempts:
        problems.append("budget echo mismatch")
    if raw["status"] not in ("RUN_FOUND", "RUN_NO_HIT"):
        problems.append("bad status %r" % raw["status"])
    elapsed = raw["elapsed_seconds"]
    if elapsed > 0:
        expect = raw["completed_hashes"] / elapsed
        # elapsed 打印保留 6 位小数：亚毫秒级时打印精度不足以支撑
        # 相对 1e-3 校验（1 次哈希 ~几微秒，截断误差可达两位数百分比），
        # 此时只验证 rate 为正且与 completed 方向一致。
        if elapsed >= 0.001:
            if abs(raw["hash_rate"] - expect) > max(1.0, expect * 1e-3):
                problems.append("hash_rate != completed/elapsed")
        elif raw["completed_hashes"] > 0 and raw["hash_rate"] <= 0:
            problems.append("hash_rate <= 0 with completed > 0")
    if raw["found"] and raw["completed_hashes"] > raw["scheduled_attempts"]:
        problems.append("hit but completed > scheduled")
    return problems


class BudgetContractTestBase(unittest.TestCase):
    """需要真实 GPU + CUDA 二进制的基类；不可用时 SKIP。"""

    def setUp(self):
        runner = GPURunner(BINARY)
        if not runner.available():
            self.skipTest(
                "GPU 环境不可用（无 %s）：预算边界实测标记 SKIP/NOT_RUN" % BINARY
            )
        self.runner = runner
        self.header = genesis_header()

    def mine(self, mode, max_attempts, target=None, start_nonce=0, seconds=60.0):
        return self.runner.mine(
            self.header,
            target if target is not None else int(TARGET_NEVER_HIT, 16),
            start_nonce=start_nonce,
            seconds=seconds,
            max_attempts=max_attempts,
            mode=mode,
        )


class TestSearchBudget(BudgetContractTestBase):
    """search 模式：completed <= scheduled <= max_attempts（精确窗口）。"""

    def test_max_attempts_1(self):
        raw = self.mine("search", 1)
        self.assertLessEqual(raw["completed_hashes"], 1)
        self.assertLessEqual(raw["scheduled_attempts"], 1)
        self.assertEqual(_invariant_ok(raw, 1), [])

    def test_max_attempts_1000(self):
        raw = self.mine("search", 1000)
        self.assertLessEqual(raw["completed_hashes"], 1000)
        self.assertLessEqual(raw["scheduled_attempts"], 1000)
        self.assertEqual(_invariant_ok(raw, 1000), [])

    def test_max_attempts_16383(self):
        raw = self.mine("search", 16383)
        self.assertLessEqual(raw["scheduled_attempts"], 16383)
        self.assertLessEqual(raw["completed_hashes"], 16383)
        self.assertEqual(_invariant_ok(raw, 16383), [])

    def test_max_attempts_16384(self):
        raw = self.mine("search", 16384)
        self.assertLessEqual(raw["scheduled_attempts"], 16384)
        self.assertLessEqual(raw["completed_hashes"], 16384)
        self.assertEqual(_invariant_ok(raw, 16384), [])

    def test_max_attempts_16385(self):
        raw = self.mine("search", 16385)
        self.assertLessEqual(raw["scheduled_attempts"], 16385)
        self.assertLessEqual(raw["completed_hashes"], 16385)
        self.assertEqual(_invariant_ok(raw, 16385), [])

    def test_exact_budget_when_no_hit(self):
        """不命中条件下：scheduled == completed == 预算（精确执行）。"""
        for budget in (1, 1000, 16383, 16384, 16385):
            raw = self.mine("search", budget)
            self.assertEqual(raw["scheduled_attempts"], budget, "budget=%d" % budget)
            self.assertEqual(raw["completed_hashes"], budget, "budget=%d" % budget)
            self.assertEqual(raw["reason"], "max-attempts")
            self.assertEqual(_invariant_ok(raw, budget), [])

    def test_early_hit_completed_le_scheduled(self):
        """提前命中：completed <= scheduled（同一窗口内提前退出）。"""
        raw = self.mine("search", 1 << 40,
                        target=int(TARGET_ALWAYS_HIT, 16), seconds=10.0)
        self.assertTrue(raw["found"])
        self.assertLessEqual(raw["completed_hashes"], raw["scheduled_attempts"])
        self.assertEqual(_invariant_ok(raw, raw["max_attempts_budget"]), [])

    def test_last_nonce_boundary(self):
        """start-nonce=2^32-1：最多计算最后 1 个 Nonce。"""
        raw = self.mine("search", 1000000,
                        target=int(TARGET_ALWAYS_HIT, 16),
                        start_nonce=(1 << 32) - 1)
        self.assertLessEqual(raw["completed_hashes"], 1)
        self.assertLessEqual(raw["scheduled_attempts"], 1)
        self.assertTrue(raw["found"])
        self.assertEqual(raw["nonce"], (1 << 32) - 1)
        self.assertEqual(_invariant_ok(raw, raw["max_attempts_budget"]), [])

    def test_time_limit_reason_and_stats(self):
        """时间限制触发：正常退出、reason=time-limit、统计完整。"""
        raw = self.mine("search", 1 << 40, seconds=0.5)
        self.assertEqual(raw["reason"], "time-limit")
        self.assertFalse(raw["found"])
        self.assertGreater(raw["completed_hashes"], 0)
        self.assertEqual(_invariant_ok(raw, raw["max_attempts_budget"]), [])


class TestFixedWorkBudget(BudgetContractTestBase):
    """fixed-work 模式：恰好完成预算个哈希（无命中判定）。"""

    def test_max_attempts_1(self):
        raw = self.mine("fixed-work", 1)
        self.assertEqual(raw["completed_hashes"], 1)
        self.assertEqual(raw["scheduled_attempts"], 1)
        self.assertEqual(_invariant_ok(raw, 1), [])

    def test_max_attempts_1000(self):
        raw = self.mine("fixed-work", 1000)
        self.assertEqual(raw["completed_hashes"], 1000)
        self.assertEqual(raw["scheduled_attempts"], 1000)
        self.assertEqual(_invariant_ok(raw, 1000), [])

    def test_max_attempts_16385(self):
        raw = self.mine("fixed-work", 16385)
        self.assertEqual(raw["completed_hashes"], 16385)
        self.assertEqual(raw["scheduled_attempts"], 16385)
        self.assertEqual(_invariant_ok(raw, 16385), [])

    def test_budget_exhausted_before_rounds(self):
        """预算先于 rounds 耗尽：reason=max-attempts，精确完成。"""
        raw = self.mine("fixed-work", 100000, seconds=30.0)
        # rounds 默认不传 → 不限轮数；预算 100000 先触发
        self.assertEqual(raw["reason"], "max-attempts")
        self.assertEqual(raw["completed_hashes"], 100000)
        self.assertEqual(raw["scheduled_attempts"], 100000)

    def test_rounds_exhausted_before_budget(self):
        """rounds 先于预算耗尽：reason=rounds-done。"""
        raw = self.runner.mine(
            self.header, None, start_nonce=0, seconds=30.0,
            max_attempts=1 << 40, mode="fixed-work", rounds=3,
        )
        self.assertEqual(raw["reason"], "rounds-done")
        self.assertEqual(raw["rounds"], 3)
        self.assertEqual(_invariant_ok(raw, raw["max_attempts_budget"]), [])

    def test_time_limit_reason_and_stats(self):
        raw = self.mine("fixed-work", 1 << 40, seconds=0.5)
        self.assertEqual(raw["reason"], "time-limit")
        self.assertEqual(raw["completed_hashes"], raw["scheduled_attempts"])
        self.assertEqual(_invariant_ok(raw, raw["max_attempts_budget"]), [])


class TestParamRejection(unittest.TestCase):
    """参数拒绝不依赖 GPU：Python 侧预校验 + 二进制校验双保险。"""

    def test_python_rejects_start_nonce_overflow(self):
        runner = GPURunner(BINARY)
        with self.assertRaises(GpuParameterError):
            runner.validate_inputs(seconds=5, max_attempts=10, start_nonce=1 << 32)

    def test_python_rejects_max_attempts_zero(self):
        runner = GPURunner(BINARY)
        with self.assertRaises(GpuParameterError):
            runner.validate_inputs(seconds=5, max_attempts=0, start_nonce=0)

    def test_binary_rejects_when_available(self):
        runner = GPURunner(BINARY)
        if not runner.available():
            self.skipTest("GPU 环境不可用：SKIP/NOT_RUN")
        header = genesis_header()
        with self.assertRaises(GpuParameterError):
            runner.mine(header, 1, start_nonce=1 << 32, seconds=5,
                        max_attempts=10)
        with self.assertRaises(GpuParameterError):
            runner.mine(header, 1, start_nonce=0, seconds=5, max_attempts=0)


if __name__ == "__main__":
    unittest.main()
