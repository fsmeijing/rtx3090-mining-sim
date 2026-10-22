# docs/ 教学文档索引

面向初中生的比特币工作量证明（SHA-256d）教学系列，全部内容与
本仓库代码、真实链上数据、真实实测报告一一对应。

| # | 文档 | 主题 |
|---|---|---|
| 01 | [区块与区块头](01-block-and-header.md) | 80 字节区块头六字段、字节序 |
| 02 | [SHA-256 工作原理](02-sha256.md) | 搅拌机比喻、双重 SHA-256 |
| 03 | [Nonce 和 ExtraNonce](03-nonce-and-extranonce.md) | 挖矿旋钮、4 字节上限 |
| 04 | [创世区块](04-genesis-block.md) | 高度 0、泰晤士报标题、复算 |
| 05 | [区块 #1 的产生](05-block-1.md) | 链条如何扣上、复刻玩法 |
| 06 | [Merkle Root](06-merkle-root.md) | 交易指纹、淘汰赛比喻 |
| 07 | [nBits 和难度目标](07-nbits-and-difficulty.md) | 压缩目标、三档教学难度 |
| 08 | [H 与 T 的整数比较](08-hash-vs-target.md) | 完整 256-bit 比较、字节序坑 |
| 09 | [CPU 与 GPU 的计算差异](09-cpu-vs-gpu.md) | 教授 vs 小学生、7 万倍差距 |
| 10 | [RTX 3090 算力测试](10-rtx3090-benchmark.md) | 真实实测数据与解读 |
| 11 | [实验操作指南](11-lab-guide.md) | 7 个动手实验 |
| 12 | [常见错误排查](12-troubleshooting.md) | 运行/编译/理解三类 FAQ |
| 附 | [高度 0–19 区块对照表](blocks-0-19-table.md) | 20 个真实区块数据 |

数据与代码的对应关系：每个示例数字都来自 `bitcoin_pow/data/blocks_0_19.json`
（真实链上数据）、`reports/benchmark_rtx3090_*.json`（真实实测），
或可由 `python3 -m bitcoin_pow` 命令现场复现。
