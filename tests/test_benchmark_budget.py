# -*- coding: utf-8 -*-
"""benchmark 预算传递与正确性门禁回归测试。

回归目标：
1. run_benchmark() 必须把用户指定的 max_attempts 传给 runner.mine()，
   禁止"参数传入了但底层用 1 << 40 忽略"（历史 bug）。
2. max_attempts_budget.per_run 与各次运行的 max_attempts_budget_per_run
   必须一致（都等于实际传递并被二进制执行的预算）。
3. correctness_check 只有在 GPU 确实命中（found=True）且 CPU 复核通过
   时才允许 PASS；未命中为 NOT_VERIFIED；复核不一致为 FAIL。
4. 真机测试：max-attempts=1/1000/16385 时每次 fixed-work 运行实际完成
   数量不超过预算（无 GPU 环境显式 SKIP）。
"""

import os
import unittest
from unittest import mock

import bitcoin_pow.benchmark as bm
from bitcoin_pow.block_header import genesis_header
from bitcoin_pow.genesis import search_nonce
from bitcoin_pow.gpu import GPU_NOT_RUN
from bitcoin_pow.target import mode_target

BINARY = os.environ.get("SHA256D_MINER", "cuda/build/sha256d_miner")


class _FakeGPURunner:
    """记录 mine() 调用参数的假 runner；按脚本返回 canned JSON。"""

    calls = []           # [(mode, kwargs), ...]
    script = []          # 每次调用依次弹出的响应；耗尽则用 default_factory

    def __init__(self, binary):
        self.binary = binary
        self.available_calls = []

    def available(self):
        return True

    @classmethod
    def reset(cls, responses, default_factory):
        cls.calls = []
        cls.script = list(responses)
        cls._default_factory = default_factory

    def mine(self, header, target=None, start_nonce=0, seconds=30.0,
             max_attempts=1 << 40, mode="search", rounds=None):
        _FakeGPURunner.calls.append({
            "mode": mode, "target": target,
            "start_nonce": start_nonce, "seconds": seconds,
            "max_attempts": max_attempts, "rounds": rounds,
        })
        if _FakeGPURunner.script:
            return _FakeGPURunner.script.pop(0)(max_attempts)
        return _FakeGPURunner._default_factory(max_attempts)


def _fixed_response(max_attempts):
    """模拟真实二进制的 fixed-work 输出：echo 预算，completed == min(预算, 500)。"""
    completed = min(max_attempts, 500)
    return {
        "status": "RUN_NO_HIT", "mode": "fixed-work",
        "device_name": "FAKE", "sm_count": 1,
        "cuda_runtime_version": "12.4", "driver_version": "12.4",
        "max_attempts_budget": max_attempts,          # 二进制 echo 实际预算
        "start_nonce": 0, "end_nonce": completed,
        "scheduled_attempts": completed, "completed_hashes": completed,
        "rounds": 1, "elapsed_seconds": 0.001,
        "hash_rate": completed / 0.001,
        "found": False, "nonce": 0, "hash_hex": "", "reason": "max-attempts",
    }


class TestBudgetPassThrough(unittest.TestCase):
    """回归：用户预算必须透传到 mine()，不得被 1 << 40 覆盖。"""

    def setUp(self):
        _FakeGPURunner.reset([], _fixed_response)
        patcher = mock.patch.object(bm, "GPURunner", _FakeGPURunner)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_user_budget_passed_to_mine(self):
        report = bm.run_benchmark(gpu=True, binary="fake", max_attempts=16385,
                                  fixed_runs=2, fixed_rounds=5, seconds=5.0)
        fixed_calls = [c for c in _FakeGPURunner.calls if c["mode"] == "fixed-work"]
        self.assertEqual(len(fixed_calls), 2)
        for c in fixed_calls:
            self.assertEqual(c["max_attempts"], 16385,
                             "fixed-work mine() 未收到用户预算")
        # per_run 与逐次 echo 一致
        fw = report["gpu"]["fixed_workload"]
        self.assertEqual(fw["max_attempts_budget"]["per_run"], 16385)
        for run in fw["results"]:
            self.assertEqual(run["max_attempts_budget_per_run"], 16385)
            self.assertLessEqual(run["completed_hashes"], 16385)

    def test_default_budget_passes_hardcap_not_silently_changed(self):
        """默认预算（1<<40）也应原样透传（有效预算 = min(用户, 2^40)）。"""
        bm.run_benchmark(gpu=True, binary="fake", fixed_runs=1, seconds=5.0)
        self.assertEqual(_FakeGPURunner.calls[-1]["max_attempts"], 1 << 40)

    def test_correctness_check_budget_is_independent(self):
        """正确性检验阶段的预算与测速预算明确区分。"""
        # 预设：第 1 次调用是 check（found=True），其后是 fixed-work
        hit = search_nonce(genesis_header(), mode_target("easy"),
                           start_nonce=0, max_attempts=1 << 20)
        self.assertTrue(hit.found)

        def check_response(max_attempts):
            return {
                "status": "RUN_FOUND", "mode": "search",
                "device_name": "FAKE", "sm_count": 1,
                "cuda_runtime_version": "12.4", "driver_version": "12.4",
                "max_attempts_budget": max_attempts,
                "start_nonce": 0, "end_nonce": hit.attempts,
                "scheduled_attempts": hit.attempts,
                "completed_hashes": hit.attempts,
                "rounds": 1, "elapsed_seconds": 0.001,
                "hash_rate": hit.attempts / 0.001,
                "found": True, "nonce": hit.nonce, "hash_hex": hit.hash_hex,
                "reason": "found",
            }

        _FakeGPURunner.reset([check_response], _fixed_response)
        report = bm.run_benchmark(gpu=True, binary="fake", max_attempts=1000,
                                  fixed_runs=1, seconds=5.0)
        check_call = _FakeGPURunner.calls[0]
        self.assertEqual(check_call["mode"], "search")
        # 独立预算：check 使用自己的 1<<32，不占用用户的 1000
        self.assertEqual(check_call["max_attempts"], 1 << 32)
        fixed_call = _FakeGPURunner.calls[1]
        self.assertEqual(fixed_call["max_attempts"], 1000)
        self.assertEqual(
            report["gpu"]["correctness_check"]["independent_budget"]["attempts"],
            1 << 32)
        self.assertEqual(report["gpu"]["correctness_check"]["value"], "PASS")


class TestCorrectnessGate(unittest.TestCase):
    """门禁：PASS 当且仅当 found=True 且 CPU 复核通过。"""

    def _run_with_check_response(self, response_factory):
        _FakeGPURunner.reset([response_factory], _fixed_response)
        patcher = mock.patch.object(bm, "GPURunner", _FakeGPURunner)
        patcher.start()
        self.addCleanup(patcher.stop)
        return bm.run_benchmark(gpu=True, binary="fake", max_attempts=1000,
                                fixed_runs=1, seconds=5.0)

    def test_not_found_must_not_be_pass(self):
        """GPU 未命中：CPU 复核平凡返回 True 也绝不能报 PASS。"""
        def no_hit(max_attempts):
            return {
                "status": "RUN_NO_HIT", "mode": "search",
                "device_name": "FAKE", "sm_count": 1,
                "cuda_runtime_version": "12.4", "driver_version": "12.4",
                "max_attempts_budget": max_attempts,
                "start_nonce": 0, "end_nonce": 0,
                "scheduled_attempts": 0, "completed_hashes": 0,
                "rounds": 1, "elapsed_seconds": 0.001, "hash_rate": 0.0,
                "found": False, "nonce": 0, "hash_hex": "",
                "reason": "max-attempts",
            }

        report = self._run_with_check_response(no_hit)
        self.assertEqual(report["gpu"]["correctness_check"]["value"],
                         "NOT_VERIFIED")
        self.assertNotEqual(report["gpu"]["correctness_check"]["value"], "PASS")
        self.assertFalse(report["gpu"]["correctness_check"]["gpu_found"])

    def test_wrong_hit_hash_must_be_fail(self):
        """命中但哈希与 CPU 复核不一致：FAIL。"""
        def bad_hit(max_attempts):
            return {
                "status": "RUN_FOUND", "mode": "search",
                "device_name": "FAKE", "sm_count": 1,
                "cuda_runtime_version": "12.4", "driver_version": "12.4",
                "max_attempts_budget": max_attempts,
                "start_nonce": 0, "end_nonce": 1,
                "scheduled_attempts": 1, "completed_hashes": 1,
                "rounds": 1, "elapsed_seconds": 0.001, "hash_rate": 1000.0,
                "found": True, "nonce": 0, "hash_hex": "f" * 64,  # 伪报哈希
                "reason": "found",
            }

        report = self._run_with_check_response(bad_hit)
        self.assertEqual(report["gpu"]["correctness_check"]["value"], "FAIL")

    def test_real_hit_passes(self):
        """真实命中 + CPU 复核一致：PASS。"""
        hit = search_nonce(genesis_header(), mode_target("easy"),
                           start_nonce=0, max_attempts=1 << 20)
        self.assertTrue(hit.found)

        def real_hit(max_attempts):
            return {
                "status": "RUN_FOUND", "mode": "search",
                "device_name": "FAKE", "sm_count": 1,
                "cuda_runtime_version": "12.4", "driver_version": "12.4",
                "max_attempts_budget": max_attempts,
                "start_nonce": 0, "end_nonce": hit.attempts,
                "scheduled_attempts": hit.attempts,
                "completed_hashes": hit.attempts,
                "rounds": 1, "elapsed_seconds": 0.001,
                "hash_rate": hit.attempts / 0.001,
                "found": True, "nonce": hit.nonce, "hash_hex": hit.hash_hex,
                "reason": "found",
            }

        report = self._run_with_check_response(real_hit)
        self.assertEqual(report["gpu"]["correctness_check"]["value"], "PASS")
        self.assertTrue(report["gpu"]["correctness_check"]["gpu_found"])
        self.assertTrue(report["gpu"]["correctness_check"]["cpu_recheck"])


class TestRealGpuBudget(unittest.TestCase):
    """真机验收：max-attempts=1/1000/16385（无 GPU 环境显式 SKIP）。"""

    def setUp(self):
        runner = bm.GPURunner(BINARY)
        if not runner.available():
            self.skipTest("GPU 环境不可用（无 %s）：SKIP/NOT_RUN" % BINARY)

    def _check(self, budget):
        report = bm.run_benchmark(gpu=True, binary=BINARY,
                                  max_attempts=budget, fixed_runs=1,
                                  fixed_rounds=5, seconds=10.0)
        self.assertNotEqual(report["gpu_status"], GPU_NOT_RUN)
        fw = report["gpu"]["fixed_workload"]
        self.assertEqual(fw["max_attempts_budget"]["per_run"], budget)
        for run in fw["results"]:
            self.assertEqual(run["max_attempts_budget_per_run"], budget,
                             "per_run 与逐次 echo 不一致")
            self.assertLessEqual(run["completed_hashes"], budget,
                                 "实际完成超过预算")
            self.assertLessEqual(run["scheduled_attempts"], budget)
        # 正确性检验独立预算：不受测速预算限制，应真实命中并 PASS
        self.assertEqual(report["gpu"]["correctness_check"]["value"], "PASS")
        return report

    def test_budget_1(self):
        self._check(1)

    def test_budget_1000(self):
        self._check(1000)

    def test_budget_16385(self):
        self._check(16385)


if __name__ == "__main__":
    unittest.main()
