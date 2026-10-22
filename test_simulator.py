# -*- coding: utf-8 -*-
"""simulator.py 的单元测试。运行：python3 -m unittest discover -v"""

import io
import json
import math
import unittest
from contextlib import redirect_stdout

import simulator


def run_sim(argv):
    args = simulator.parse_args(argv)
    return simulator.simulate(args)


class TestSimulate(unittest.TestCase):
    def test_deterministic_with_seed(self):
        d1, s1 = run_sim(["--days", "30", "--seed", "42"])
        d2, s2 = run_sim(["--days", "30", "--seed", "42"])
        self.assertEqual(s1, s2)
        self.assertEqual(d1, d2)

    def test_record_fields_and_magnitude(self):
        daily, summary = run_sim(["--days", "10", "--seed", "1"])
        self.assertEqual(len(daily), 10)
        r = daily[0]
        for key in ("day", "price", "network_th", "coins", "revenue",
                    "power_cost", "profit", "cumulative"):
            self.assertIn(key, r)
        self.assertGreater(r["coins"], 0)
        self.assertGreater(r["revenue"], 0)
        self.assertGreater(r["power_cost"], 0)
        self.assertEqual(r["day"], 1)
        self.assertEqual(summary["days"], 10)
        self.assertTrue(math.isfinite(summary["net_profit"]))

    def test_cumulative_matches_sum(self):
        daily, _ = run_sim(["--days", "50", "--seed", "7"])
        total = sum(r["profit"] for r in daily)
        last = daily[-1]["cumulative"]
        # 每日记录均四舍五入到 2 位小数，50 天累计最多 ~0.25 的舍入误差
        self.assertAlmostEqual(total, last, delta=len(daily) * 0.005 + 0.01)

    def test_higher_electricity_lower_profit(self):
        _, low = run_sim(["--days", "90", "--seed", "3", "--electricity", "0.2"])
        _, high = run_sim(["--days", "90", "--seed", "3", "--electricity", "1.0"])
        self.assertGreater(low["net_profit"], high["net_profit"])

    def test_scaling_gpus_increases_power_cost(self):
        _, one = run_sim(["--days", "60", "--seed", "5", "--gpus", "1"])
        _, six = run_sim(["--days", "60", "--seed", "5", "--gpus", "6"])
        self.assertAlmostEqual(one["total_power_cost"] * 6,
                               six["total_power_cost"], delta=0.5)
        self.assertAlmostEqual(one["hardware_cost"] * 6,
                               six["hardware_cost"], delta=0.5)

    def test_roi_earlier_with_higher_price(self):
        _, low_price = run_sim(["--days", "730", "--seed", "9", "--price", "1000"])
        _, high_price = run_sim(["--days", "730", "--seed", "9", "--price", "8000"])
        if low_price["roi_day"] and high_price["roi_day"]:
            self.assertLessEqual(high_price["roi_day"], low_price["roi_day"])


class TestOutput(unittest.TestCase):
    def test_report_and_json_export(self):
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.json")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = simulator.main(["--days", "5", "--seed", "11", "--json", path])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("RTX 3090", out)
            self.assertIn("净利润", out)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("summary", data)
            self.assertEqual(len(data["daily"]), 5)


if __name__ == "__main__":
    unittest.main()
