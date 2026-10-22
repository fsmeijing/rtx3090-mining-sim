# RTX 3090 Bitcoin SHA-256d 算力实测报告

> 生成时间：2026-10-22（本地实测，benchmark schema v2）｜
> 全部数值为真实测量，来源标签见 `reports/benchmark_rtx3090_*.json`。
> 本报告不含任何虚构 benchmark，不报告无可靠模型的"理论 SHA-256d 算力"。

## 1. 测量环境（MEASURED）

| 项目 | 值 | 来源 |
|---|---|---|
| GPU | NVIDIA GeForce RTX 3090 24GB | MEASURED（nvidia-smi + cudaDeviceProp） |
| SM 数量 | 82 | MEASURED |
| 驱动版本 | 580.178.04 | MEASURED（nvidia-smi） |
| CUDA Runtime | 13.0 | MEASURED（cudaRuntimeGetVersion） |
| 编译工具链 | nvcc V13.0.88（用户空间 conda 工具链，无 sudo） | MEASURED |
| 编译架构 | sm_86（Ampere） | MEASURED |
| 测量时 GPU 状态 | 33°C / ~40W / 桌面空闲 | MEASURED（nvidia-smi） |

## 2. 固定工作量 Benchmark（MEASURED，推荐口径）

**方法**（`--benchmark`，schema v2）：
- 正确性检验：search 模式 easy 目标命中 Nonce 后，CPU 用 hashlib 重建
  区块头复算比对 → `correctness_check: PASS`（证明内核算的是真实 SHA256d）；
- 吞吐测量：`fixed-work` 模式，**无 H≤T 判定、无提前退出**，Nonce 范围由
  `--start-nonce` 与轮数预设（32-bit 上界处截断并如实报告），
  受 `--seconds` 上限约束；重复 3 次，统计吞吐量。

| 模式 | min | median | max | 3 次累计 completed_hashes |
|---|---:|---:|---:|---:|
| medium（20 轮/次） | 3.53 GH/s | **3.53 GH/s** | 3.94 GH/s | 1,289,748,480 |
| genesis（20 轮/次） | 3.72 GH/s | **3.74 GH/s** | 3.93 GH/s | 1,289,748,480 |

- `hash_rate = completed_hashes / elapsed_seconds`（MEASURED）
- `scheduled_attempts` 与 `completed_hashes` 在 JSON 中分离；
  固定工作量模式下两者相等（无提前退出）；搜索模式命中时
  completed < scheduled（命中后线程提前退出），差异如实保留。

## 3. 搜索模式实测（MEASURED，教学口径）

| 模式 | scheduled | completed | 用时 | 结果 | CPU 复核 |
|---|---:|---:|---:|---|---|
| genesis（真实创世难度） | 2,085,093,376 | 2,085,068,640 | 0.555 s | 命中 **Nonce 2,083,236,893** | PASS |
| easy | 21,495,808 | 36,064 | 极短 | 命中（提前退出） | PASS |

创世模式命中哈希（完整 64 位十六进制，与主网完全一致）：

```
000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
```

**这是本实验最重要的教学证据**：GPU 从 Nonce 0 开始按线程切分扫描，
在真实创世目标下命中了 2009 年中本聪使用的同一个 Nonce（2,083,236,893）。

注意 genesis 搜索的 completed（2,085,068,640）略小于 scheduled
（2,085,093,376）：命中后同一 launch 内剩余线程提前退出，
差值 24,736 被诚实保留，不计入算力。

搜索模式（尤其命中即停的短跑）的 H/s 只反映"含启动开销的完成量/时间"，
**不能作为持续算力口径**；持续算力请以上方固定工作量 benchmark 为准。

## 4. 理论吞吐量分层（THEORETICAL，仅供量级参考）

严格区分三个层次（JSON 键 `theoretical_breakdown`）：

| 层次 | 值 | 说明 |
|---|---|---|
| 1. 整数操作吞吐量 | 82×128×1.70GHz ≈ **17.8 T INT32 ops/s** | 芯片规格推算（每核每周期 1 次 INT32），与哈希率无直接换算 |
| 2. SHA-256 压缩吞吐量 | ≈ 17.8T / ~750 ops ≈ **23.7 G compressions/s（绝对上界量级）** | 假设"每周期每核 1 次整数运算 + 每压缩 ~750 ops"，为**不可达的绝对上界**，不构成预测 |
| 3. **SHA-256d 哈希吞吐量** | **不报告**（`null`） | 每压缩真实运算数、寄存器压力、调度开销无法从规格可靠推算——**无可靠模型就不给数字** |

历史上本仓库曾把"17.8 TH/s"错误地当作 SHA-256d 理论上界，并据此称
"实测距上界 3–5 倍"——该说法已被删除：17.8 TH/s 只是第 1 层的整数
操作吞吐量，与 SHA-256d H/s 之间不存在"3–5 倍"这种可靠换算关系。

## 5. 复现命令

```bash
# 编译（sm_86，支持 CUDA_HOME 用户空间工具链）
scripts/build_cuda.sh

# 固定工作量 benchmark（推荐口径，多次运行统计）
python3 -m bitcoin_pow --benchmark --mode genesis --gpu --seconds 15 --json reports/benchmark_rtx3090_genesis.json

# 搜索模式复现创世命中（确定性，Nonce 从 0 顺序扫描）
python3 -m bitcoin_pow --mode genesis --gpu --seconds 60

# 退出码契约：0=正常（含未命中） 2=参数错误 3=CUDA 错误
```

## 6. 与旧收益模拟器的算力数据区分

- 旧 `simulator.py`（收益数学模拟）中的 120 MH/s 是 **ETHash 算法**的教学
  模拟参数，属于 `TEACHING_SIM` 类别；
- 本报告的 3.5–3.9 GH/s 是 **Bitcoin SHA-256d** 的真实测量值（`MEASURED`）；
- 两者算法不同、来源不同，禁止互相冒充。
