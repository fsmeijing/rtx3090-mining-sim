# -*- coding: utf-8 -*-
"""GPU 契约测试（无需 GPU：NOT_RUN 路径 + CPU 复核门禁注入用例）。"""

import unittest

from bitcoin_pow.block_header import genesis_header
from bitcoin_pow.gpu import GPURunner, GpuUnavailableError, recheck_gpu_result
from bitcoin_pow.sha256d import block_header_hash, to_display_hex
from bitcoin_pow.target import GENESIS_TARGET


def _easy_target():
    return GENESIS_TARGET << 24


class TestGpuUnavailable(unittest.TestCase):
    def test_missing_binary_raises(self):
        runner = GPURunner("/nonexistent/sha256d_miner")
        self.assertFalse(runner.available())
        with self.assertRaises(GpuUnavailableError):
            runner.mine(genesis_header(), _easy_target())

    def test_benchmark_reports_not_run(self):
        from bitcoin_pow.benchmark import run_benchmark

        report = run_benchmark(gpu=True, binary="/nonexistent/sha256d_miner")
        self.assertIn("NOT_RUN", report["gpu_status"])
        self.assertIsNone(report["gpu"])

    def test_benchmark_without_gpu_flag_is_cpu_reference(self):
        from bitcoin_pow.benchmark import run_benchmark

        report = run_benchmark(gpu=False)
        self.assertIn("NOT_RUN", report["gpu_status"])
        self.assertEqual(report["cpu_reference"]["source"], "MEASURED")
        self.assertGreater(report["cpu_reference"]["attempts"], 0)


class TestCpuRecheckGate(unittest.TestCase):
    """GPU 结果必须经 CPU 复核：命中必须逐字节一致且 H<=T。"""

    def setUp(self):
        self.header = genesis_header()
        self.target = _easy_target()

    def test_not_found_passes_trivially(self):
        self.assertTrue(recheck_gpu_result(
            self.header, self.target,
            {"found": False, "nonce": None, "hash_hex": None},
        ))

    def test_correct_hit_passes(self):
        # 用 CPU 计算一个真实满足 H<=T 的解，模拟 GPU 报告
        from bitcoin_pow.genesis import search_nonce

        res = search_nonce(self.header, self.target, start_nonce=0, max_attempts=1 << 20)
        self.assertTrue(res.found)
        raw = {"found": True, "nonce": res.nonce, "hash_hex": res.hash_hex}
        self.assertTrue(recheck_gpu_result(self.header, self.target, raw))

    def test_injected_wrong_hash_fails(self):
        """注入错误哈希：复核必须 FAIL（防伪门禁）。"""
        from bitcoin_pow.genesis import search_nonce

        res = search_nonce(self.header, self.target, start_nonce=0, max_attempts=1 << 20)
        self.assertTrue(res.found)
        bad = {"found": True, "nonce": res.nonce,
               "hash_hex": "f" * 64}   # 伪报哈希
        self.assertFalse(recheck_gpu_result(self.header, self.target, bad))

    def test_injected_target_violation_fails(self):
        """真实哈希但不满足 H<=T 的声明：复核 FAIL。"""
        # 找一个不满足目标的 Nonce（Nonce=0 在 easy 模式下大概率不满足）
        digest = block_header_hash(self.header.with_nonce(0).serialize())
        hex0 = to_display_hex(digest)
        if int.from_bytes(digest, "big") <= self.target:
            self.skipTest("Nonce 0 恰好命中（概率 ~1/256），换用门禁用例")
        raw = {"found": True, "nonce": 0, "hash_hex": hex0}
        self.assertFalse(recheck_gpu_result(self.header, self.target, raw))


if __name__ == "__main__":
    unittest.main()
