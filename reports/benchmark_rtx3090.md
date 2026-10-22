# RTX 3090 Bitcoin SHA-256d 算力实测报告

> 生成时间：2026-10-22（本地实测，benchmark schema v2 + 精确预算 v3）｜
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

## 2. 精确预算契约（v3，先于一切算力数字）

Host 端为每轮 launch 确定精确 Nonce 窗口 `[window_start, window_end)`：
`window_end = min(start + 剩余预算, 2^32, start + GPU单轮覆盖)`，窗口上界
传入 Kernel，窗口外的线程/迭代**不执行任何 SHA-256d**：

```
completed_hashes <= scheduled_attempts <= max_attempts   （恒成立）
scheduled_attempts = Σ(window_end - window_start)        （精确分配）
completed_hashes   = 内核 atomicAdd 实际完成数
hash_rate          = completed / elapsed                 （MEASURED）
```

max-attempts 语义（CLI/JSON/OpenSpec/文档一致）：**每次运行的预算**
（多次 benchmark 各次独立享有，非共享总额）。

## 3. 固定工作量 Benchmark（MEASURED，推荐口径）

**方法**（`--benchmark`）：
- 正确性检验：search 模式 easy 目标命中 Nonce 后，CPU 用 hashlib 重建
  区块头复算比对 → `correctness_check: PASS`；
- 吞吐测量：`fixed-work` 模式，**无 H≤T 判定、无命中提前退出**，
  受 max-attempts（每次运行）/ rounds（20 轮）/ seconds 三限约束，
  reason 记录最早触发者；重复 3 次。

| 模式 | min | median | max | 每次运行 completed | reasons |
|---|---:|---:|---:|---:|---|
| medium | 3.42 GH/s | **4.00 GH/s** | 4.01 GH/s | 429,916,160 | rounds-done ×3 |
| genesis | 3.23 GH/s | **3.38 GH/s** | 3.54 GH/s | 429,916,160 | rounds-done ×3 |

每次运行 scheduled_attempts == completed_hashes == 429,916,160
（= 20 轮 × 82SM×16块×256线程×64迭代，每次运行预算 2^32 未先耗尽）。

## 3.1 预算参数传递验收（MEASURED，2026-10-22 修复后）

`--benchmark --gpu --max-attempts N`（每次 fixed_runs=3，JSON 见
`reports/benchmark_budget_N.json`）；正确性检验 PASS（独立预算 1<<32，
与测速预算严格区分）：

| max-attempts | per_run | 逐次 echo | 每次实际 completed | reason |
|---:|---:|---:|---:|---|
| 1 | 1 | 1 ×3 | 1（≤1） | max-attempts |
| 1000 | 1000 | 1000 ×3 | 1000（≤1000） | max-attempts |
| 16385 | 16385 | 16385 ×3 | 16385（≤16385） | max-attempts |

## 4. 预算边界实测（MEASURED，逐项）

| max-attempts | scheduled | completed | reason | 不变式 |
|---:|---:|---:|---|---|
| 1 | 1 | 1 | max-attempts | OK |
| 1000 | 1000 | 1000 | max-attempts | OK |
| 16383 | 16383 | 16383 | max-attempts | OK |
| 16384 | 16384 | 16384 | max-attempts | OK |
| 16385 | 16385 | 16385 | max-attempts | OK |
| start-nonce=2³²−1（必然命中目标） | 1 | 1 | found | OK |
| 提前命中（easy） | 21,495,808 | 35,744 | found | completed ≤ scheduled |
| time-limit（0.5s） | 1,633,681,408 | 1,633,681,408 | time-limit | OK |
| space 耗尽（3s 时限） | 4,294,967,296 | 4,294,967,296 | nonce-space-exhausted | OK |

search 与 fixed-work 两种模式均验证；JSON 原始数据见
`reports/budget_search_*.json`、`reports/budget_fixed_*.json`。

## 5. 搜索模式实测（MEASURED，教学口径）

| 模式 | scheduled | completed | 用时 | 结果 | CPU 复核 |
|---|---:|---:|---:|---|---|
| genesis（真实创世难度） | 2,085,093,376 | 2,085,042,688 | 0.640 s | 命中 **Nonce 2,083,236,893** | PASS |
| easy | 21,495,808 | 35,744 | 极短 | 命中（提前退出） | PASS |

创世模式命中哈希（完整 64 位十六进制，与主网完全一致）：

```
000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
```

**这是本实验最重要的教学证据**：GPU 从 Nonce 0 开始按线程切分扫描，
在真实创世目标下命中了 2009 年中本聪使用的同一个 Nonce（2,083,236,893）。

genesis 搜索的 completed（2,085,042,688）小于 scheduled
（2,085,093,376）：命中后同一窗口内剩余线程提前退出，差值如实保留。

## 6. 理论吞吐量分层（THEORETICAL，仅供量级参考）

严格区分三个层次（JSON 键 `theoretical_breakdown`）：

| 层次 | 值 | 说明 |
|---|---|---|
| 1. 整数操作吞吐量 | 82×128×1.70GHz ≈ **17.8 T INT32 ops/s** | 芯片规格推算（每核每周期 1 次 INT32），与哈希率无直接换算 |
| 2. SHA-256 压缩吞吐量 | ≈ 17.8T / ~750 ops ≈ **23.7 G compressions/s（绝对上界量级）** | 假设"每周期每核 1 次整数运算 + 每压缩 ~750 ops"，为**不可达的绝对上界**，不构成预测 |
| 3. **SHA-256d 哈希吞吐量** | **不报告**（`null`） | 每压缩真实运算数、寄存器压力、调度开销无法从规格可靠推算——**无可靠模型就不给数字** |

历史上本仓库曾把"17.8 TH/s"错误地当作 SHA-256d 理论上界，并据此称
"实测距上界 3–5 倍"——该说法已被删除：17.8 TH/s 只是第 1 层的整数
操作吞吐量，与 SHA-256d H/s 之间不存在"3–5 倍"这种可靠换算关系。

## 7. 复现命令

```bash
# 编译（sm_86，支持 CUDA_HOME 用户空间工具链）
scripts/build_cuda.sh

# 固定工作量 benchmark（推荐口径，每次运行预算 = max-attempts，3 次重复）
python3 -m bitcoin_pow --benchmark --mode genesis --gpu --seconds 10 --json reports/benchmark_rtx3090_genesis.json

# 搜索模式复现创世命中（确定性）
python3 -m bitcoin_pow --mode genesis --gpu --seconds 60

# 预算边界（示例）
cuda/build/sha256d_miner --header-hex <160hex> --target-hex <64hex> \
    --mode search --start-nonce 0 --max-attempts 16385 --seconds 10 --json

# 退出码契约：0=正常（含未命中） 2=参数错误 3=CUDA 错误
```

## 8. 与旧收益模拟器的算力数据区分

- 旧 `simulator.py`（收益数学模拟）中的 120 MH/s 是 **ETHash 算法**的教学
  模拟参数，属于 `TEACHING_SIM` 类别；
- 本报告的 3.4–3.5 GH/s 是 **Bitcoin SHA-256d** 的真实测量值（`MEASURED`）；
- 两者算法不同、来源不同，禁止互相冒充。
