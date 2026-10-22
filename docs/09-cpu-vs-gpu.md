# 9. CPU 与 GPU 的计算差异

## 一句话总览

CPU 像几位**教授**：单个很强、什么都会；
GPU 像**两万多名小学生**：每位只会简单算术，但人多力量大。
SHA-256 挖矿恰好是"海量重复的简单算术"——正是 GPU 的主场。

## 它们分别怎么挖矿？

**CPU（本仓库 `bitcoin_pow/genesis.py`）**：一个循环，逐个 Nonce 试：

```python
for nonce in range(start, end):
    digest = sha256d(header_with_nonce(nonce))
    if int_value(digest) <= target: return nonce
```

Python 参考实现实测约 **17 万 H/s**（hashlib 已是 C 实现，
瓶颈在 Python 解释器循环本身；换成纯 C 单线程约几百万 H/s）。

**GPU（本仓库 `cuda/main.cu`）**：一次"发射"数万个线程同时算：

```
线程 tid 负责 Nonce：start + tid×64 ... start + tid×64 + 63
每线程 64 次尝试，一次 launch 共 82SM×16块×256线程×64 ≈ 2150 万次
```

RTX 3090 固定工作量 benchmark 实测 **3.4–3.5 GH/s**（持续口径，见 docs/10）——
是 Python CPU 参考实现的约 **2 万倍**。

## 为什么 GPU 这么快？

| 维度 | CPU | GPU |
|---|---|---|
| 核心数 | 8–64 个大核 | RTX 3090：82 SM × 128 = 10496 个 CUDA 核 |
| 单核能力 | 强（乱序执行、大缓存、分支预测） | 弱（简单流水线、小缓存） |
| 擅长 | 逻辑复杂、分支多的任务 | 大量相同、无依赖的并行计算 |
| 挖矿时的分工 | 串行试 Nonce | 每个线程领一段 Nonce 区间 |

SHA-256 挖矿的每个 Nonce 计算**互不依赖**（试哪个都行），
所以可以完美并行——这叫"尴尬并行"（embarrassingly parallel）。

## GPU 版 SHA-256 有什么讲究？

本仓库内核（`cuda/sha256d.cuh`）的三个关键优化：

1. **全程寄存器**：80 字节头 + 64 轮压缩全在寄存器里展开，
   不访问显存（显存访问慢寄存器几百倍）；
2. **常量放只读缓存**：64 个轮常量 K 放 `__constant__` 内存；
3. **字节序一次搞定**：Nonce 写入和结果展示时做 `bswap32`，
   语义与 CPU 参考实现逐位一致（这是本项目调试中踩过的真实的坑，
   详见 docs/12 排错篇）。

## 验证不对称性：算一次难，验证一次易

无论 CPU 还是 GPU：找到满足 H ≤ T 的 Nonce 平均要试几十亿次，
但**验证**只需要算一次 SHA256d。本项目强制执行：

```
GPU 报告命中 → CPU 用 hashlib 重算一次 → 一致才宣布成功（CPU 复核 PASS）
```

这模拟了比特币全网的运行方式：矿工狂算，全节点一算便知。

## 动手对比

```bash
# CPU 参考（约 17 万 H/s）
python3 -m bitcoin_pow --mode easy --max-attempts 1000000
# GPU（固定工作量口径约 3.4–3.5 GH/s）
python3 -m bitcoin_pow --benchmark --mode genesis --gpu --seconds 15
```

同样的题面、同样的判定规则——只是"工人数量"不同。
