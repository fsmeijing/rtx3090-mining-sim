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

`fixed-work` 模式：**无 H≤T 判定、无提前退出**，Nonce 范围预先确定
（32-bit 上界处截断并如实报告），重复 3 次统计吞吐量：

| 模式 | min | median | max | 3 次累计 completed |
|---|---:|---:|---:|---:|
| medium | 3.53 GH/s | 3.53 GH/s | 3.94 GH/s | 1,289,748,480 |
| genesis | 3.72 GH/s | 3.74 GH/s | 3.93 GH/s | 1,289,748,480 |

统计契约（诚实算力的关键）：

- `scheduled_attempts` = 已分配给 GPU 的工作量；
- `completed_hashes` = 内核**实际完成**的哈希数（atomicAdd 累计）；
- `hash_rate = completed_hashes / elapsed_seconds`；
- **提前退出的线程工作量不计入完成数** —— 绝不把"分配了"当"算完了"。

## 搜索模式（教学口径）

| 模式 | scheduled | completed | 用时 | 结果 | CPU 复核 |
|---|---:|---:|---:|---|---|
| genesis（真实创世难度） | 2,085,093,376 | 2,085,068,640 | 0.555 s | 命中 Nonce **2,083,236,893** | PASS |
| easy | 21,495,808 | 36,064 | 极短 | 命中后提前退出 | PASS |

创世命中哈希（与主网一致）：

```
000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
```

**最有说服力的一件事**：genesis 模式下 GPU 从 Nonce 0 顺序扫描，
0.555 秒后命中的正是 2009 年中本聪使用的 Nonce 2,083,236,893。
这不是巧合：创世区块头固定、满足 H≤T 的 Nonce 集合确定，
我们的内核与真实比特币 SHA-256d 逐位一致，必然重新发现历史。

注意 completed（2,085,068,640）比 scheduled（2,085,093,376）少的
24,736 次是命中后提前退出的线程工作量——如实保留差异，不虚报。

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
| 3.5–3.9 GH/s | Bitcoin SHA-256d | MEASURED | 本报告 |

ETHash 和 SHA-256d 是完全不同的算法，算力数字不可比、不可互换。

## 复现本测试

```bash
scripts/build_cuda.sh                     # 编译 sm_86
python3 -m bitcoin_pow --benchmark --mode genesis --gpu --seconds 15
python3 -m bitcoin_pow --mode genesis --gpu --seconds 60
```

完整 JSON 报告：`reports/benchmark_rtx3090_medium.json`、
`reports/benchmark_rtx3090_genesis.json`（schema v2）。
