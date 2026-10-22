#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RTX 3090 挖矿收益模拟器 / RTX 3090 Mining Profitability Simulator

纯 Python 标准库实现（无第三方依赖），用于模拟 GPU 挖矿的收益与回本周期。

模型说明：
- 币价：几何布朗运动（GBM）随机游走
- 全网算力：按日指数增长（难度递增）
- 收益：按个人算力占全网算力比例瓜分出块奖励
- 成本：按 GPU 功耗 * 24h * 电价 逐日计算电费，可叠加矿池费率
- 输出：逐日收益表、回本天数、ASCII 收益曲线、JSON 导出

仅用于教学与娱乐模拟，不构成任何投资建议。
"""

import argparse
import json
import math
import random
import sys

# ---------------------------------------------------------------------------
# GPU 型号档案（参数为典型 ETHash/ETCHash 挖矿数据，仅供模拟参考）
# ---------------------------------------------------------------------------
GPUS = {
    "rtx3090":   {"name": "NVIDIA RTX 3090",    "hashrate_mhs": 120.0, "power_w": 350, "price": 5000},
    "rtx3090ti": {"name": "NVIDIA RTX 3090 Ti", "hashrate_mhs": 134.0, "power_w": 420, "price": 6500},
    "rtx3080":   {"name": "NVIDIA RTX 3080",    "hashrate_mhs": 98.0,  "power_w": 320, "price": 4200},
    "rtx3070":   {"name": "NVIDIA RTX 3070",    "hashrate_mhs": 61.0,  "power_w": 220, "price": 3000},
    "rtx3060ti": {"name": "NVIDIA RTX 3060 Ti", "hashrate_mhs": 61.0,  "power_w": 200, "price": 2600},
    "rx6800xt":  {"name": "AMD RX 6800 XT",     "hashrate_mhs": 63.0,  "power_w": 230, "price": 3800},
}


def gpu_choice(s):
    if s not in GPUS:
        raise argparse.ArgumentTypeError(
            "未知 GPU 型号：%s（可选：%s）" % (s, ", ".join(GPUS))
        )
    return s


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="RTX 3090 挖矿收益模拟器（蒙特卡洛逐日模拟）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--gpu", type=gpu_choice, default="rtx3090", help="GPU 型号")
    p.add_argument("--gpus", type=int, default=1, help="GPU 数量（矿机规模）")
    p.add_argument("--days", type=int, default=365, help="模拟天数")
    p.add_argument("--price", type=float, default=3000.0, help="初始币价（货币单位）")
    p.add_argument("--drift", type=float, default=0.0, help="币价年化漂移（0.1=年涨10%%）")
    p.add_argument("--vol", type=float, default=0.80, help="币价年化波动率")
    p.add_argument("--network-th", type=float, default=900.0, help="初始全网算力（TH/s）")
    p.add_argument("--difficulty-growth", type=float, default=0.002,
                   help="全网算力日增长率（0.002=日增0.2%%）")
    p.add_argument("--reward", type=float, default=2.0, help="每块奖励（币）")
    p.add_argument("--block-time", type=float, default=13.3, help="出块间隔（秒）")
    p.add_argument("--electricity", type=float, default=0.5, help="电价（元/kWh）")
    p.add_argument("--pool-fee", type=float, default=0.01, help="矿池费率（0.01=1%%）")
    p.add_argument("--gpu-price", type=float, default=None,
                   help="单卡购入价（默认取 GPU 档案价）")
    p.add_argument("--seed", type=int, default=None, help="随机种子（可复现）")
    p.add_argument("--table-every", type=int, default=30, help="逐日明细表打印间隔（天）")
    p.add_argument("--json", metavar="PATH", default=None, help="将逐日结果导出为 JSON 文件")
    return p.parse_args(argv)


def simulate(args):
    """运行逐日模拟，返回 (daily_records, summary)。"""
    rng = random.Random(args.seed)
    gpu = GPUS[args.gpu]
    n = max(1, args.gpus)

    my_mhs = gpu["hashrate_mhs"] * n
    hardware_cost = args.gpu_price * n if args.gpu_price else gpu["price"] * n

    # GBM 逐日参数
    mu_d = (args.drift - 0.5 * args.vol ** 2) / 365.0
    sigma_d = args.vol / math.sqrt(365.0)

    price = args.price
    network_th = args.network_th
    cumulative = 0.0
    total_revenue = 0.0
    total_power_cost = 0.0
    total_coins = 0.0
    roi_day = None
    daily = []

    for day in range(1, args.days + 1):
        price *= math.exp(mu_d + sigma_d * rng.gauss(0, 1))
        network_th *= (1.0 + args.difficulty_growth)

        blocks_per_day = 86400.0 / args.block_time
        share = my_mhs / (network_th * 1e6)          # MH/s -> TH/s 比例
        coins = args.reward * blocks_per_day * share * (1.0 - args.pool_fee)
        revenue = coins * price
        power_cost = gpu["power_w"] * n / 1000.0 * 24.0 * args.electricity
        profit = revenue - power_cost
        cumulative += profit
        total_revenue += revenue
        total_power_cost += power_cost
        total_coins += coins

        if roi_day is None and cumulative >= hardware_cost:
            roi_day = day

        daily.append({
            "day": day,
            "price": round(price, 4),
            "network_th": round(network_th, 2),
            "coins": coins,
            "revenue": round(revenue, 2),
            "power_cost": round(power_cost, 2),
            "profit": round(profit, 2),
            "cumulative": round(cumulative, 2),
        })

    summary = {
        "gpu": gpu["name"],
        "gpus": n,
        "total_hashrate_mhs": my_mhs,
        "hardware_cost": hardware_cost,
        "days": args.days,
        "total_coins": round(total_coins, 6),
        "total_revenue": round(total_revenue, 2),
        "total_power_cost": round(total_power_cost, 2),
        "net_profit": round(total_revenue - total_power_cost, 2),
        "roi_day": roi_day,
        "final_price": round(daily[-1]["price"], 4),
        "final_network_th": round(network_th, 2),
    }
    return daily, summary


def render_chart(daily, width=60):
    """将累计收益渲染为 ASCII 竖条图（按列取点，按行打印）。"""
    values = [r["cumulative"] for r in daily]
    step = max(1, len(values) // width)
    sampled = values[::step]
    lo, hi = min(sampled), max(sampled)
    if math.isclose(lo, hi):
        lo, hi = lo - 1.0, hi + 1.0
    rows = 12
    lines = []
    for row in range(rows, 0, -1):
        level = lo + (hi - lo) * (row - 0.5) / rows
        line = "".join("#" if v >= level else " " for v in sampled)
        label = "%12.0f |" % level
        lines.append(label + line)
    lines.append(" " * 13 + "-" * len(sampled))
    lines.append(" " * 13 + "第1天" + " " * (len(sampled) - 7) + "第%d天" % len(values))
    return "\n".join(lines)


def print_report(daily, summary, args):
    gpu = GPUS[args.gpu]
    print("=" * 66)
    print("  %s x %d  |  挖矿收益模拟  |  %d 天  (seed=%s)"
          % (gpu["name"], summary["gpus"], summary["days"], args.seed))
    print("=" * 66)
    print("  总算力: %.0f MH/s   硬件投入: %.0f   电价: %.2f 元/kWh"
          % (summary["total_hashrate_mhs"], summary["hardware_cost"], args.electricity))
    print("-" * 66)
    header = ("  %5s %10s %12s %12s %12s %12s"
              % ("天", "币价", "日收益", "日电费", "日净利", "累计净利"))
    print(header)
    for r in daily:
        if r["day"] == 1 or r["day"] % args.table_every == 0 or r["day"] == len(daily):
            print("  %5d %10.2f %12.2f %12.2f %12.2f %12.2f"
                  % (r["day"], r["price"], r["revenue"], r["power_cost"],
                     r["profit"], r["cumulative"]))
    print("-" * 66)
    print("  总产出: %.4f 币   总收入: %.2f   总电费: %.2f"
          % (summary["total_coins"], summary["total_revenue"], summary["total_power_cost"]))
    print("  净利润: %.2f   回本天数: %s"
          % (summary["net_profit"],
             ("%d 天" % summary["roi_day"]) if summary["roi_day"] else "未能回本"))
    print("  期末币价: %.2f   期末全网算力: %.0f TH/s"
          % (summary["final_price"], summary["final_network_th"]))
    print("-" * 66)
    print("  累计净利曲线：")
    print(render_chart(daily))
    print("=" * 66)
    print("  * 本模拟仅用于教学与娱乐，不构成投资建议。")


def main(argv=None):
    args = parse_args(argv)
    daily, summary = simulate(args)
    print_report(daily, summary, args)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "daily": daily}, f,
                      ensure_ascii=False, indent=2)
        print("  * 逐日结果已导出: %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
