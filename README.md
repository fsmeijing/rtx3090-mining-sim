# RTX 3090 Bitcoin SHA-256d Mining Simulator

> **两个独立模块，一个仓库：**
> 1. **Bitcoin PoW 教学实验平台**（v0.1.0，本项目主体）：用真实的比特币创世区块数据，让 RTX 3090 实际执行双重 SHA-256 工作量证明计算 —— 完全离线，CPU 可独立复核。
> 2. **挖矿收益数学模拟器**（原有功能，保留）：纯 Python 标准库的 GPU 挖矿收益/回本模拟，不执行任何真实哈希计算。

## 模块一：Bitcoin SHA-256d PoW 教学实验平台

### 这是什么？

一个演示比特币工作量证明（Proof-of-Work）核心机制的离线实验环境：

```
80字节区块头 → SHA256(SHA256(·)) → 256-bit 哈希 H
                                     │
0x1d00ffff → 解码 → 256-bit 目标 T ──┴→ H ≤ T ? ──是──▶ 挖到！
                                     │否
                                     ▼
                                  Nonce+1 继续
```

- 使用**真实的创世区块数据**（Version=1、MerkleRoot=4a5e…a33b、Timestamp=1231006505、nBits=0x1d00ffff、Nonce=2083236893）
- GPU 实测可**复现真实创世哈希** `000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f`（见 [reports/benchmark_rtx3090.md](reports/benchmark_rtx3090.md)）
- 内置比特币主网高度 0–19 共 20 个真实区块测试向量
- 所有 GPU 结果必须通过 **CPU 独立复核**（hashlib 重算比对）才被承认

### 快速开始（无需显卡）

```bash
python3 -m bitcoin_pow --verify          # 复算创世区块 → MATCH
python3 -m bitcoin_pow --mode easy       # CPU 亲手挖矿（~256 次尝试）
python3 -m bitcoin_pow --mode medium     # 难度提高（~100 万次）
python3 -m unittest discover -v          # 全部测试（含 20 区块复算）
```

### GPU 实验（RTX 3090，sm_86）

```bash
scripts/build_cuda.sh                    # 编译（支持 CUDA_HOME 用户空间工具链）
python3 -m bitcoin_pow --mode genesis --gpu --seconds 60   # 0.6 秒"重挖"创世区块
python3 -m bitcoin_pow --benchmark --mode genesis --gpu --seconds 30 --json reports/my.json
```

CLI 完整支持：`--verify` / `--mode easy|medium|genesis` / `--benchmark` / `--seconds` / `--max-attempts` / `--gpu` / `--binary` / `--json` / `--seed`。

### 实测算力（真实测量，非理论值）

| 模式 | 累计尝试 | 用时 | 实测算力 | CPU 复核 |
|---|---:|---:|---:|---|
| easy | 21,495,808 | ~0.002 s | 11.92 GH/s | PASS |
| medium | 21,495,808 | ~0.004 s | 5.59 GH/s | PASS |
| genesis（真实创世难度） | 2,085,093,376 | 0.640 s | 3.26 GH/s | PASS，命中 Nonce 2,083,236,893 |

理论推算上界约 17.8 TH/s（THEORETICAL），实测 3.3–11.9 GH/s（MEASURED），
两类数值在报告中以来源标签严格区分，详见 [reports/benchmark_rtx3090.md](reports/benchmark_rtx3090.md)。

### 目录结构

```
bitcoin_pow/          CPU 参考实现（Python，零依赖）+ CLI + GPU 契约
cuda/                 CUDA C++17 内核（sha256d.cuh, main.cu, CMakeLists.txt）
tests/                单元测试（向量/边界/门禁/离线安全）
scripts/              build_cuda.sh、fetch_real_blocks.py
docs/                 12 篇面向初中生的教学文档 + 数据对照表
reports/              RTX 3090 实测报告（JSON + Markdown）
openspec/             OpenSpec 规格（7 个 capability，strict 验证通过）
.github/workflows/    CI（CPU 测试 + CUDA 编译门禁；GPU 实测标记 NOT_RUN）
simulator.py 等       原有收益模拟器（保留）
```

### 教学文档

从 [docs/README.md](docs/README.md) 进入：区块头、SHA-256、Nonce、创世区块、
区块 #1、Merkle Root、nBits、H/T 比较、CPU/GPU 差异、算力实测、操作指南、排错。

### 离线与安全承诺

- **不连接**矿池、比特币 P2P 网络或任何 HTTP 服务（CI 中有静态扫描测试）
- **不处理**钱包、私钥或真实交易
- 未运行 GPU 实测的环境一律显式标记 `GPU_STATUS: NOT_RUN`，**绝不伪造实测数据**
- 本项目仅用于教学与娱乐，不构成任何投资建议

---

## 模块二：挖矿收益数学模拟器（原有功能）

> 注意：此模块是**收益数学模拟**，不执行真实哈希运算；其中的 120 MH/s
> 是 ETHash 算法的教学模拟参数（`TEACHING_SIM`），与模块一测得的
> Bitcoin SHA-256d 实测算力（`MEASURED`）分属不同算法，不可混用。

纯 Python 标准库实现的 GPU 挖矿收益模拟器（无需显卡即可运行）。

### 功能特性

- 内置 RTX 3090 / 3090 Ti / 3080 / 3070 / 3060 Ti / RX 6800 XT 典型挖矿档案（算力、功耗、价格）
- 币价：几何布朗运动（GBM）随机游走，可设定年化漂移与波动率
- 全网算力：按日指数增长（模拟难度递增）
- 收益：按个人算力占全网比例瓜分出块奖励，可设矿池费率
- 电费：按功耗 × 24h × 电价逐日计算
- 输出：逐日明细表、回本天数、ASCII 累计收益曲线、JSON 导出
- 支持随机种子，结果完全可复现；多卡规模模拟
- 零第三方依赖，Python ≥ 3.8 即可运行

### 快速开始

```bash
# 默认：单张 RTX 3090，模拟 365 天
python3 simulator.py

# 6 卡矿机，365 天，固定随机种子（可复现）
python3 simulator.py --gpus 6 --days 365 --seed 42

# 自定义参数：初始币价 3000、年波动率 80%、电价 0.5 元/kWh、导出 JSON
python3 simulator.py --seed 7 --price 3000 --vol 0.8 --electricity 0.5 --json result.json
```

### 模型说明

| 项 | 公式 |
|---|---|
| 币价（日） | `P(t+1) = P(t) · exp(μ/365 + σ/√365 · N(0,1))` |
| 全网算力（日） | `H_net(t+1) = H_net(t) · (1 + g)` |
| 日产出（币） | `reward · (86400 / block_time) · H_mine / H_net` |
| 日收入 | `日产出 · 币价 · (1 − 矿池费率)` |
| 日电费 | `功耗(kW) · 24 · 电价` |
| 回本天数 | 累计净利首次 ≥ 硬件投入的天数 |

---

## 运行测试 / Tests

```bash
python3 -m unittest discover -v    # 全部：新 PoW 测试 + 原模拟器回归
```

## License

MIT
