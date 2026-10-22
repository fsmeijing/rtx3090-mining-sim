# 11. 实验操作指南

> 全程离线。不需要比特币客户端、不需要钱包、不连接任何网络服务。
> 显卡不是必需的——没有 GPU 也能完成大部分实验。

## 0. 环境准备

```bash
git clone https://github.com/fsmeijing/rtx3090-mining-sim.git
cd rtx3090-mining-sim
python3 --version          # 需要 Python >= 3.8，本项目零第三方依赖
```

有 RTX 3090（或其他 NVIDIA 卡）想跑 GPU 实验的，先编译 CUDA 程序：
参见 docs/12 的"编译 CUDA 程序"一节。

## 实验 1：验证创世区块（必做，1 分钟）

```bash
python3 -m bitcoin_pow --verify
```

观察：六字段表、计算 H、期望哈希、`MATCH`。
思考：程序没联网，它凭什么知道"答案"？——因为 2009 年后全世界
都记录着这个哈希，我们只是重新算了一遍。

## 实验 2：亲手挖矿（CPU 版，理解循环）

```bash
python3 -m bitcoin_pow --mode easy --max-attempts 100000
python3 -m bitcoin_pow --mode medium --max-attempts 2000000
```

观察：medium 模式的尝试次数应该在几十万量级（期望 ~100 万）。
多做几次，记录每次的尝试次数——这就是"挖矿运气"的抽样。

## 实验 3：体会难度（CPU 版碰壁体验）

```bash
python3 -m bitcoin_pow --mode genesis --max-attempts 10000000
```

观察：1000 万次尝试后如实报告"未找到解"。难度 1 需要期望 43 亿次。
**体会**：2010 年代初的 CPU 矿工面对的就是这道题。

## 实验 4：GPU 重演历史（有 RTX 3090 时，1 分钟）

```bash
python3 -m bitcoin_pow --mode genesis --gpu --seconds 60
```

观察：约 0.6 秒、20.8 亿次尝试后命中 Nonce 2,083,236,893，
哈希与创世区块完全一致，CPU 复核 PASS。

## 实验 5：测量算力（GPU benchmark）

```bash
python3 -m bitcoin_pow --benchmark --mode genesis --gpu --seconds 30 \
    --json reports/my_benchmark.json
```

观察输出的 JSON：每个数值都带 `MEASURED` 或 `THEORETICAL` 标签。
对照 `reports/benchmark_rtx3090.md` 检查数量级是否合理。

## 实验 6：阅读代码

| 想理解什么 | 看哪里 |
|---|---|
| 80 字节区块头怎么拼 | `bitcoin_pow/block_header.py` |
| 双重 SHA-256 | `bitcoin_pow/sha256d.py`（3 行核心） |
| 目标解码与比较 | `bitcoin_pow/target.py` |
| 挖矿循环 | `bitcoin_pow/genesis.py` 的 `search_nonce` |
| GPU 内核 | `cuda/sha256d.cuh` |
| GPU/CPU 契约 | `bitcoin_pow/gpu.py` |

## 实验 7：跑全部测试

```bash
python3 -m unittest discover -v
```

预期：全部 OK（含 20 个真实区块复算、边界比较、CPU 复核门禁、
离线安全扫描、旧收益模拟器回归）。

## 安全须知

- 本项目**永远不联网**：不连矿池、不连比特币网络（可审计代码，见 tests/test_offline_safety.py）；
- 不涉及任何真实钱包、私钥、交易；
- 长时间满载 GPU 会发热，笔记本用户注意散热；
- 所有结论都可以用 `--verify` 和单元测试独立复核——**不要相信，要验证**。
