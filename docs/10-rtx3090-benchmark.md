# 10. RTX 3090 算力测试（真实测量）

> 本页所有数字来自 `reports/` 下的实测报告，来源标签 `MEASURED`。
> 没有任何虚构或"理论加成"的数字冒充实测；不报告无可靠模型的
> "理论 SHA-256d 算力"。

## 测试环境

| 项目 | 值 |
|---|---|
| GPU | NVIDIA GeForce RTX 3090 24GB（Ampere，82 SM，sm_86） |
| 驱动 | 580.178.04 |
| CUDA Runtime | 13.0（nvcc V13.0.88，用户空间 conda 工具链编译） |
| 桌面负载 | 空闲（33°C，约 40W，另接显示器） |

## 固定工作量 Benchmark（推荐口径）

`fixed-work` 模式：**无 H≤T 判定、无命中提前退出**，受
max-attempts（每次运行的预算）/ rounds / seconds 三重限制，
reason 记录最早触发者，重复 3 次统计吞吐量：

| 模式 | min | median | max | 每次运行 completed |
|---|---:|---:|---:|---:|
| medium | 3.42 GH/s | 3.44 GH/s | 3.46 GH/s | 429,916,160 |
| genesis | 3.11 GH/s | 3.46 GH/s | 3.49 GH/s | 429,916,160 |

精确预算契约（诚实算力的关键）：

- Host 端为每轮 launch 确定**精确 Nonce 窗口**并传入 Kernel；
  窗口外的线程/迭代**不执行任何 SHA-256d**；
- `scheduled_attempts` = 有效分配的候选 Nonce 数（精确）；
  `completed_hashes` = 内核实际完成数（atomicAdd）；
- **不变式：`completed_hashes <= scheduled_attempts <= max_attempts` 恒成立**；
- `hash_rate = completed_hashes / elapsed_seconds`；
- max-attempts 是**每次运行的预算**（多次运行各次独立享有）。

## 搜索模式（教学口径）

| 模式 | scheduled | completed | 用时 | 结果 | CPU 复核 |
|---|---:|---:|---:|---|---|
| genesis（真实创世难度） | 2,085,093,376 | 2,085,042,688 | 0.640 s | 命中 Nonce **2,083,236,893** | PASS |
| easy | 21,495,808 | 35,744 | 极短 | 命中后提前退出 | PASS |

创世命中哈希（与主网一致）：

```
000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
```

**最有说服力的一件事**：genesis 模式下 GPU 从 Nonce 0 顺序扫描，
0.640 秒后命中的正是 2009 年中本聪使用的 Nonce 2,083,236,893。
这不是巧合：创世区块头固定、满足 H≤T 的 Nonce 集合确定，
我们的内核与真实比特币 SHA-256d 逐位一致，必然重新发现历史。

注意 completed（2,085,042,688）比 scheduled（2,085,093,376）少的
50,688 次是命中后提前退出的线程工作量——如实保留差异，不虚报。

## 理论吞吐量分层（THEORETICAL）

严格分三层，各说各话：

| 层次 | 值 | 性质 |
|---|---|---|
| 整数操作吞吐量 | ≈ 17.8 T INT32 ops/s | 芯片规格推算，**不是哈希率** |
| SHA-256 压缩吞吐量 | ≈ 23.7 G compressions/s | 绝对上界量级（每压缩 ~750 ops 的理想化假设），不可达 |
| **SHA-256d 哈希吞吐量** | **不报告（null）** | 无可靠理论模型；唯一可信数字是 MEASURED |

> 勘误：早期版本曾把 17.8 TH/s 当作"SHA-256d 理论上界"并称实测
> "距上界 3–5 倍"。该说法是错误的类别混用，已删除。

## 退出码与状态契约

| GPU_STATUS | 含义 | found | 统计数据 |
|---|---|---|---|
| GPU_NOT_RUN | 未执行（无二进制/无 GPU） | — | 不产出任何数值 |
| GPU_ERROR | 参数错误（exit 2）或 CUDA 错误（exit 3） | — | 不产出可信数值 |
| GPU_RUN_NO_HIT | 正常执行，未找到合格哈希 | false | attempts/elapsed/rate 全部保留 |
| GPU_RUN_FOUND | 正常执行且命中 | true | 需 CPU 复核 PASS 才算成功 |

## 这些数字和旧模拟器里的 120 MH/s 是一回事吗？

不是，而且要特别小心：

| 数字 | 算法 | 类别 | 出处 |
|---|---|---|---|
| 120 MH/s | ETHash（以太坊时代算法） | TEACHING_SIM | 旧 `simulator.py` 收益模拟参数 |
| 3.4–3.5 GH/s | Bitcoin SHA-256d | MEASURED | 本报告 |

ETHash 和 SHA-256d 是完全不同的算法，算力数字不可比、不可互换。

## 复现本测试

```bash
scripts/build_cuda.sh                     # 编译 sm_86
python3 -m bitcoin_pow --benchmark --mode genesis --gpu --seconds 15
python3 -m bitcoin_pow --mode genesis --gpu --seconds 60
```

完整 JSON 报告：`reports/benchmark_rtx3090_medium.json`、
`reports/benchmark_rtx3090_genesis.json`（schema v2）。
