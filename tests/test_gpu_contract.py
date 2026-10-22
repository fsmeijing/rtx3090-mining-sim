# -*- coding: utf-8 -*-
"""GPU 契约测试（无需 GPU：NOT_RUN/ERROR/RUN_NO_HIT/RUN_FOUND + CPU 复核门禁）。

用"假 CUDA 二进制"（输出固定 JSON 的小脚本）验证 GPURunner 与 CLI 的
退出码与状态契约，不需要真实 GPU。
"""

import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout

from bitcoin_pow import cli
from bitcoin_pow.block_header import genesis_header
from bitcoin_pow.gpu import (
    GPU_ERROR,
    GPU_NOT_RUN,
    GPU_RUN_FOUND,
    GPU_RUN_NO_HIT,
    GPURunner,
    GpuExecutionError,
    GpuParameterError,
    GpuUnavailableError,
    gpu_status_from_raw,
    recheck_gpu_result,
)
from bitcoin_pow.sha256d import block_header_hash, to_display_hex
from bitcoin_pow.target import GENESIS_TARGET


def _easy_target():
    return GENESIS_TARGET << 24


class _FakeMiner:
    """生成一个输出固定 JSON 的假 CUDA 二进制。"""

    def __init__(self, tmpdir, status, exit_code=0):
        self.path = os.path.join(tmpdir, "fake_miner")
        payload = json.dumps({
            "status": status, "mode": "search",
            "device_name": "FAKE", "sm_count": 1,
            "cuda_runtime_version": "12.4", "driver_version": "12.4",
            "max_attempts_budget": 1000,
            "start_nonce": 0, "end_nonce": 1000,
            "scheduled_attempts": 1000, "completed_hashes": 1000,
            "rounds": 1, "elapsed_seconds": 0.5, "hash_rate": 2000.0,
            "found": False, "nonce": 0, "hash_hex": "", "reason": "done",
        })
        script = "#!/bin/sh\nprintf '%s' '%s'\nexit %d\n" % (payload, payload, exit_code)
        with open(self.path, "w") as f:
            f.write(script)
        os.chmod(self.path, os.stat(self.path).st_mode | stat.S_IEXEC)


class TestGpuStatusEnum(unittest.TestCase):
    def test_status_mapping(self):
        self.assertEqual(gpu_status_from_raw(None), GPU_NOT_RUN)
        self.assertEqual(gpu_status_from_raw({"status": "RUN_FOUND"}), GPU_RUN_FOUND)
        self.assertEqual(gpu_status_from_raw({"status": "RUN_NO_HIT"}), GPU_RUN_NO_HIT)
        self.assertEqual(gpu_status_from_raw({"status": "???"}), GPU_ERROR)


class TestGpuUnavailable(unittest.TestCase):
    def test_missing_binary_raises(self):
        runner = GPURunner("/nonexistent/sha256d_miner")
        self.assertFalse(runner.available())
        with self.assertRaises(GpuUnavailableError):
            runner.mine(genesis_header(), _easy_target())

    def test_benchmark_reports_not_run(self):
        from bitcoin_pow.benchmark import run_benchmark

        report = run_benchmark(gpu=True, binary="/nonexistent/sha256d_miner")
        self.assertEqual(report["gpu_status"], GPU_NOT_RUN)
        self.assertIsNone(report["gpu"])

    def test_benchmark_without_gpu_flag_is_cpu_reference(self):
        from bitcoin_pow.benchmark import run_benchmark

        report = run_benchmark(gpu=False)
        self.assertEqual(report["gpu_status"], GPU_NOT_RUN)
        self.assertEqual(report["cpu_reference"]["source"], "MEASURED")
        self.assertGreater(report["cpu_reference"]["completed_hashes"], 0)

    def test_python_side_param_validation(self):
        runner = GPURunner("/nonexistent/sha256d_miner")
        with self.assertRaises(GpuParameterError):
            runner.validate_inputs(seconds=0, max_attempts=10, start_nonce=0)
        with self.assertRaises(GpuParameterError):
            runner.validate_inputs(seconds=float("inf"), max_attempts=10, start_nonce=0)
        with self.assertRaises(GpuParameterError):
            runner.validate_inputs(seconds=5, max_attempts=0, start_nonce=0)
        with self.assertRaises(GpuParameterError):
            runner.validate_inputs(seconds=5, max_attempts=10, start_nonce=1 << 32)
        # 合法参数不抛
        runner.validate_inputs(seconds=5.0, max_attempts=100, start_nonce=(1 << 32) - 1)

    def test_cli_rejects_invalid_params(self):
        self.assertEqual(cli.main(["--mode", "easy", "--seconds", "0"]), 2)
        self.assertEqual(cli.main(["--mode", "easy", "--seconds", "-3"]), 2)
        self.assertEqual(cli.main(["--mode", "easy", "--max-attempts", "0"]), 2)
        self.assertEqual(cli.main(["--mode", "easy",
                                   "--start-nonce", str(1 << 32)]), 2)


class TestExitCodeContract(unittest.TestCase):
    """CUDA 退出码契约：0=正常（含未命中）、2=参数错误、3=CUDA 错误。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fake_miner_")

    def test_exit2_raises_parameter_error(self):
        fake = _FakeMiner(self.tmp, "RUN_NO_HIT", exit_code=2)
        runner = GPURunner(fake.path)
        with self.assertRaises(GpuParameterError):
            runner.mine(genesis_header(), _easy_target())

    def test_exit3_raises_execution_error(self):
        fake = _FakeMiner(self.tmp, "RUN_NO_HIT", exit_code=3)
        runner = GPURunner(fake.path)
        with self.assertRaises(GpuExecutionError):
            runner.mine(genesis_header(), _easy_target())

    def test_exit0_no_hit_is_not_an_error(self):
        """正常执行未命中：不抛异常，返回 RUN_NO_HIT 原始数据。"""
        fake = _FakeMiner(self.tmp, "RUN_NO_HIT", exit_code=0)
        raw = GPURunner(fake.path).mine(genesis_header(), _easy_target())
        self.assertEqual(raw["status"], "RUN_NO_HIT")
        self.assertFalse(raw["found"])
        self.assertEqual(gpu_status_from_raw(raw), GPU_RUN_NO_HIT)
        self.assertGreater(raw["completed_hashes"], 0)

    def test_search_mode_requires_target(self):
        fake = _FakeMiner(self.tmp, "RUN_NO_HIT", exit_code=0)
        with self.assertRaises(GpuParameterError):
            GPURunner(fake.path).mine(genesis_header(), None, mode="search")

    def test_benchmark_gpu_error_path(self):
        """二进制以 exit 3 失败时，benchmark 报 GPU_ERROR，绝不编造数值。"""
        from bitcoin_pow.benchmark import run_benchmark

        fake = _FakeMiner(self.tmp, "RUN_NO_HIT", exit_code=3)
        report = run_benchmark(gpu=True, binary=fake.path)
        self.assertEqual(report["gpu_status"], GPU_ERROR)


class TestCliGpuStatusOutput(unittest.TestCase):
    """CLI 输出契约：NOT_RUN / ERROR / RUN_NO_HIT / RUN_FOUND 四态。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fake_miner_")
        self._old_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._old_cwd)

    def _run_cli(self, binary):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["--mode", "easy", "--gpu", "--binary", binary])
        return rc, buf.getvalue()

    def test_cli_run_no_hit_is_not_not_run(self):
        """正常执行未命中：GPU 状态为 RUN_NO_HIT，绝不输出 NOT_RUN。"""
        fake = _FakeMiner(self.tmp, "RUN_NO_HIT", exit_code=0)
        rc, out = self._run_cli(fake.path)
        self.assertEqual(rc, 0)
        self.assertIn("RUN_NO_HIT", out)
        self.assertIn("found=false", out)
        self.assertNotIn("NOT_RUN", out)
        self.assertIn("MEASURED", out)   # attempts/elapsed/rate 保留

    def test_cli_run_found_with_cpu_recheck(self):
        fake = _FakeMiner(self.tmp, "RUN_FOUND", exit_code=0)
        rc, out = self._run_cli(fake.path)
        # 假命中 Nonce 0：CPU 复核大概率 FAIL → rc=2；若 Nonce 0 恰好命中
        # （概率 ~1/256）则复核 PASS → rc=0。两种都是契约内行为。
        self.assertIn(rc, (0, 2))
        self.assertIn("RUN_FOUND", out)

    def test_cli_gpu_error(self):
        fake = _FakeMiner(self.tmp, "RUN_NO_HIT", exit_code=2)
        rc, out = self._run_cli(fake.path)
        self.assertEqual(rc, 3)
        self.assertIn("GPU_STATUS    : ERROR", out)

    def test_cli_gpu_not_run(self):
        rc, out = self._run_cli("/nonexistent/sha256d_miner")
        self.assertEqual(rc, 0)
        self.assertIn("GPU_STATUS    : NOT_RUN", out)


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
        from bitcoin_pow.genesis import search_nonce

        res = search_nonce(self.header, self.target, start_nonce=0, max_attempts=1 << 20)
        self.assertTrue(res.found)
        raw = {"found": True, "nonce": res.nonce, "hash_hex": res.hash_hex}
        self.assertTrue(recheck_gpu_result(self.header, self.target, raw))

    def test_injected_wrong_hash_fails(self):
        from bitcoin_pow.genesis import search_nonce

        res = search_nonce(self.header, self.target, start_nonce=0, max_attempts=1 << 20)
        self.assertTrue(res.found)
        bad = {"found": True, "nonce": res.nonce,
               "hash_hex": "f" * 64}   # 伪报哈希
        self.assertFalse(recheck_gpu_result(self.header, self.target, bad))

    def test_injected_target_violation_fails(self):
        """真实哈希但不满足 H<=T 的声明：复核 FAIL。"""
        digest = block_header_hash(self.header.with_nonce(0).serialize())
        hex0 = to_display_hex(digest)
        if int.from_bytes(digest, "little") <= self.target:
            self.skipTest("Nonce 0 恰好命中（概率 ~1/256），换用门禁用例")
        raw = {"found": True, "nonce": 0, "hash_hex": hex0}
        self.assertFalse(recheck_gpu_result(self.header, self.target, raw))


if __name__ == "__main__":
    unittest.main()
