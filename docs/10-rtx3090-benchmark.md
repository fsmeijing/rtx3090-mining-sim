# 10. RTX 3090 算力测试（真实测量）

> 本页所有数字来自 `reports/` 下的实测报告，来源标签 `MEASURED`。
> 没有任何虚构或"理论加成"的数字冒充实测。

## 测试环境

| 项目 | 值 |
|---|---|
| GPU | NVIDIA GeForce RTX 3090 24GB（Ampere，82 SM，sm_86） |
| 驱动 | 580.178.04 |
| CUDA Runtime | 13.0（nvcc V13.0.88，用户空间 conda 工具链编译） |
| 桌面负载 | 空闲（33°C，约 40W，另接显示器） |

## 实测结果（2026-10-22）

| 模式 | 累计尝试 | 用时 | 实测算力 | 命中 Nonce | CPU 复核 |
|---|---:|---:|---:|---:|---|
| easy | 21,495,808 | ~0.002 s | 11.92 GH/s | 308,224 | PASS |
| medium | 21,495,808 | ~0.004 s | 5.59 GH/s | 1,085,914 | PASS |
| genesis（真实创世难度） | 2,085,093,376 | 0.640 s | 3.26 GH/s | **2,083,236,893** | PASS |

创世模式命中的哈希（与主网一致）：

```
000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
```

## 最有说服力的一件事

**genesis 模式下，GPU 从 Nonce 0 顺序扫描，0.64 秒后命中的正是
2009 年中本聪使用的 Nonce 2,083,236,893。**

这不是巧合：创世区块头是固定的，满足 H ≤ T 的 Nonce 是确定的集合，
我们的 GPU 内核与真实比特币的 SHA-256d 逐位一致，
所以"重新发明"的挖矿程序必然重新发现历史。

## 为什么不同模式测出的 H/s 不一样？

都是真实测量，但短跑和长跑不一样：

- easy/medium：单轮 launch 就命中 → 测的是"含启动开销的短时峰值"；
- genesis：连续约 97 轮 launch → 每轮间的同步/回传开销被摊进平均值；
- 内核里的"命中提前退出检查"在长运行中也有一点开销。

想要更稳定的持续算力数字，可以运行 benchmark 的固定工作量模式：

```bash
python3 -m bitcoin_pow --benchmark --mode genesis --gpu --seconds 30 --json reports/my_run.json
```

## 理论上界（THEORETICAL，仅供参考）

```
82 SM × 128 CUDA核/SM × 1.70 GHz × 1 op/cycle ≈ 17.8 TH/s（上界量级）
```

实测 3.3–11.9 GH/s 距离理论上界 3–5 倍——这就是真实内核
（数据依赖链、寄存器压力、launch 开销）与"理想芯片"的差距。
**理论上界永远不能替代实测**，报告中两者用 `THEORETICAL`/`MEASURED`
标签严格区分。

## 这些数字和旧模拟器里的 120 MH/s 是一回事吗？

不是，而且要特别小心：

| 数字 | 算法 | 类别 | 出处 |
|---|---|---|---|
| 120 MH/s | ETHash（以太坊时代算法） | TEACHING_SIM | 旧 `simulator.py` 收益模拟参数 |
| 3.3–11.9 GH/s | Bitcoin SHA-256d | MEASURED | 本报告 |

ETHash 和 SHA-256d 是完全不同的算法，算力数字不可比、不可互换。

## 复现本测试

```bash
scripts/build_cuda.sh                     # 编译 sm_86
python3 -m bitcoin_pow --benchmark --mode genesis --gpu --seconds 30
```

完整 JSON 报告：`reports/benchmark_rtx3090_medium.json`、
`reports/benchmark_rtx3090_genesis.json`。
