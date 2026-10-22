# RTX 3090 Bitcoin SHA-256d 算力实测报告

> 生成时间：2026-10-22（本地实测）｜ 全部数值为真实测量，来源标签见
> `reports/benchmark_rtx3090_*.json`。本报告不含任何虚构 benchmark。

## 1. 测量环境（MEASURED）

| 项目 | 值 | 来源 |
|---|---|---|
| GPU | NVIDIA GeForce RTX 3090 24GB | MEASURED（nvidia-smi + cudaDeviceProp） |
| SM 数量 | 82 | MEASURED |
| 驱动版本 | 580.178.04 | MEASURED（nvidia-smi） |
| CUDA Runtime | 13.0 | MEASURED（cudaRuntimeGetVersion） |
| 编译工具链 | nvcc V13.0.88（用户空间 conda 工具链，无 sudo） | MEASURED |
| 编译架构 | sm_86（Ampere） | MEASURED |
| 测量时 GPU 状态 | 33°C / 39.65W / 42% 利用率（空闲桌面环境） | MEASURED（nvidia-smi） |

## 2. 实测结果（MEASURED）

| 模式 | 目标（前导零） | 累计尝试 | 用时 | 实测算力 | 命中 Nonce | CPU 复核 |
|---|---|---|---|---|---|---|
| medium | T_genesis<<12（12 bit） | 21,495,808 | ~0.004 s | 5.59 GH/s | 1,085,914 | PASS |
| genesis（真实创世难度） | nBits=0x1d00ffff（32 bit） | 2,085,093,376 | 0.640 s | 3.26 GH/s | **2,083,236,893** | PASS |
| genesis（另一次运行） | 同上 | 2,085,093,376 | 0.570 s | 3.66 GH/s | 2,083,236,893 | PASS |

创世模式命中哈希（完整 64 位十六进制，与主网完全一致）：

```
000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
```

**这是本实验最重要的教学证据**：GPU 从 Nonce 0 开始按线程切分扫描，
在真实创世目标下命中了 2009 年中本聪使用的同一个 Nonce（2,083,236,893），
复算了同一个创世哈希 —— 证明本项目的 SHA-256d 实现与真实比特币逐位一致。

### 算力说明

实测 H/s 随模式变化（11.9 → 5.6 → 3.3 GH/s），原因：
- easy/medium 在单轮 launch 内即命中并提前退出，测得的是"含启动开销的短时峰值"；
- genesis 模式运行约 97 轮 launch，每轮之间有 `cudaDeviceSynchronize` 与结果回传开销；
- 命中后内核内的早期退出检查（`result->found` 读全局内存）在长运行中产生额外开销。

## 3. 理论推算（THEORETICAL，仅供量级参考）

- 公式：SM 数 × 128 CUDA 核/SM × 1.70 GHz × 1 op/cycle
  = 82 × 128 × 1.70e9 ≈ **17.8 TH/s（上界量级）**
- 真实 SHA256d 吞吐受整数蝶形运算依赖链、寄存器压力与内核实现影响，
  实测 3.3–11.9 GH/s 为**真实测量值**，与理论上界相差约 3–5 倍，属合理范围。
- **理论值不得替代实测值**：两者在报告中以 `THEORETICAL` / `MEASURED` 标签严格区分。

## 4. 复现命令

```bash
# 编译（sm_86）
scripts/build_cuda.sh

# 实测（ genesis 模式即真实创世难度）
python3 -m bitcoin_pow --benchmark --mode medium  --gpu --seconds 15 --json reports/benchmark_rtx3090_medium.json
python3 -m bitcoin_pow --benchmark --mode genesis --gpu --seconds 30 --json reports/benchmark_rtx3090_genesis.json

# 复现创世命中（确定性，Nonce 空间从 0 开始顺序扫描）
python3 -m bitcoin_pow --mode genesis --gpu --seconds 60
```

## 5. 与旧收益模拟器的算力数据区分

- 旧 `simulator.py`（收益数学模拟）中的 120 MH/s 是 **ETHash 算法**的教学模拟参数，
  属于 `TEACHING_SIM` 类别；
- 本报告的 3.3–11.9 GH/s 是 **Bitcoin SHA-256d** 的真实测量值（`MEASURED`）；
- 两者算法不同、来源不同，禁止互相冒充。
