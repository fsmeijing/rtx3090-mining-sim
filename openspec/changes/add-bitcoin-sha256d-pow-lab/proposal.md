# Proposal: add-bitcoin-sha256d-pow-lab

## Why

当前仓库 `simulator.py` 只做"挖矿收益数学模拟"，从未真正执行比特币的工作量证明计算。教学上需要一个完全离线的实验平台，用真实的比特币创世区块数据，让 RTX 3090 实际执行双重 SHA-256（SHA256d）哈希运算，演示"改 Nonce → 算 H → 与目标 T 比较 → 重试"的完整 PoW 流程，并测量真实 GPU 算力。仓库中现有的 ETHash 算力数据（120 MH/s）是挖矿收益模拟参数，不能冒充 RTX 3090 的 Bitcoin SHA-256d 算力，必须与新增 PoW 模块严格区分。

## What Changes

- 新增独立的 Bitcoin PoW 教学模块（不修改、不覆盖现有收益模拟器）：
  - **CPU 参考实现**（Python hashlib）：80 字节区块头序列化、SHA256d、Nonce 修改、nBits 目标解码、完整 256-bit 比较、创世区块（高度 0）复算、高度 0–19 真实区块测试向量。
  - **CUDA C++17 GPU 实现**：RTX 3090（sm_86）并行 Nonce 搜索、GPU 端双重 SHA-256 与目标比较、结果回传后由 CPU 二次验证、带运行时间与尝试次数安全上限。
  - **算力统计报告**：区分"真实测量值 / 理论推算值 / 教学模拟值"三类来源，禁止虚构 benchmark。
  - **教学文档**：面向初中生、技术准确的 Markdown 系列（区块头、SHA-256、Nonce、创世区块、Merkle、nBits、H/T 比较、CPU/GPU 差异、算力实测、操作指南、排错）。
- 新增 OpenSpec 规格集（7 个 capability）与 tasks；GitHub Actions CI 在无 GPU 环境运行 CPU 测试并验证 CUDA 源码可编译；GPU 实测作为独立门禁，未执行时显式标记 `NOT_RUN`。
- CLI 统一入口支持 `--verify`、`--mode easy|medium|genesis`、`--benchmark`、`--seconds`、`--max-attempts`。

## Impact

- Affected specs: 新增 `block-header-codec`、`sha256d-reference`、`pow-target`、`cuda-mining-simulation`、`benchmark-reporting`、`educational-documentation`、`offline-safety`
- Affected code:
  - 新增 `bitcoin_pow/`（CPU 参考实现）、`cuda/`（.cu/.hpp + CMake）、`tests/`、`scripts/`、`docs/`、`reports/`、`.github/workflows/`
  - 保留：`simulator.py`、`test_simulator.py`、`README.md`、`requirements.txt`（原功能不回归）
- 安全边界：完全离线；不连接矿池或比特币网络；不处理钱包、私钥、真实交易；不得覆盖用户未提交修改；不修改 GPU 驱动与系统环境。
