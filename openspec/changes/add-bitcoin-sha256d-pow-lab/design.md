# Design: add-bitcoin-sha256d-pow-lab

## Context

仓库现状：`simulator.py`（收益模拟，保留）、`test_simulator.py`（7 个测试，保留）、README/requirements（更新但不删除）。目标硬件为本机真实 RTX 3090（驱动 580.178.04，CUDA 13.0 能力）。开发机无系统级 CUDA Toolkit 且无 sudo 权限，因此构建脚本必须同时支持"标准 nvcc/CMake"与"用户空间工具链"，CI 上只做编译验证。

## Goals / Non-Goals

- Goals: 真实 SHA256d PoW 教学；CPU 可独立复核一切 GPU 结果；真实 GPU 算力测量；离线安全；原功能零回归。
- Non-Goals: 真实挖矿/矿池/网络通信；Stratum 协议；钱包与交易构造；性能极致优化（教学优先）；ExtraNonce（仅文档讲解概念，实验用 4 字节 Nonce）。

## Decisions

### D1. 目录结构
```
bitcoin_pow/      CPU 参考实现（Python 包）
cuda/             sha256d.cu, sha256d.hpp, CMakeLists.txt
tests/            Python 单元测试（CPU 全量 + GPU 门禁标记）
scripts/          build_cuda.sh, run_gpu_benchmark.sh, fetch_real_blocks.py
docs/             教学文档（12+ 篇）
reports/          GPU 实测报告（真实数据）
.github/workflows/ci.yml
```

### D2. 区块头编码（block-header-codec）
80 字节小端序：Version(4) + PrevHash(32) + MerkleRoot(32) + Timestamp(4) + nBits(4) + Nonce(4)。PrevHash/MerkleRoot 在内部统一以"协议字节序（小端存储）"保存；对外展示用大端十六进制（与区块浏览器一致）。nBits 解码为完整 256-bit 整数：T = mantissa × 256^(exponent−3)。

### D3. 目标与难度（pow-target）
以创世 nBits=0x1d00ffff 为基准。`--mode easy/medium/genesis` 通过左移目标构造教学目标（easy：T_genesis << 24，命中概率提高约 2^24 倍，期望约 2^8 次尝试；medium：T_genesis << 12，期望约 2^20 次；genesis：原始目标，期望约 2^32 次）。注意：目标左移后数值变大、更容易命中，但目标自身的前导零比特数变少，文档须解释"目标越大越容易"与"哈希前导零越多越小"两个方向。比较必须用完整 256-bit 整数（Python int / CUDA 128-bit×2 拆分），禁止只比前缀。

### D4. CUDA 内核（cuda-mining-simulation）
- 每线程负责 Nonce 空间的一个子区间（base_nonce + tid×iters + j），双 SHA-256 全程在寄存器内联展开（W[64] 轮函数，无共享内存依赖）。
- 命中即用 `atomicCAS` 写回首个结果（nonce + 完整 256-bit 哈希）。
- 一次 kernel launch 限制每线程迭代次数（默认 64），CPU 侧循环调度以实现 `--seconds`/`--max-attempts` 安全上限与进度输出。
- 网格：`blocks = SM 数 × 16, threads = 256`（3090 为 82 SM → 20992 线程/launch）。
- 结果必须回传 CPU 用 Python hashlib 复核后才宣布成功。

### D5. 算力报告（benchmark-reporting）
`--benchmark` 输出 JSON + Markdown：GPU 型号、CUDA 版本、驱动版本、Nonce 范围、累计尝试数、用时、H/s（换算 MH/s、GH/s）、成功哈希、目标 T、CPU 复核结论。所有数值标注来源标签：`MEASURED`（实测）/ `THEORETICAL`（理论推算）/ `TEACHING_SIM`（教学模拟）。禁止编造；无 GPU 时输出 `GPU_STATUS: NOT_RUN`。

### D6. 测试与 CI
- CPU 测试全部可在无 GPU 环境运行（unittest，与现有仓库一致）。
- 回归：现有 `test_simulator.py` 7 个测试必须继续通过。
- CI（ubuntu-latest）：装 Python + CUDA Toolkit（Jimver/cuda-toolkit），步骤：CPU 测试 → 创世复算 → 测试向量 → nBits 边界 → 模拟 Nonce 搜索正确性（CPU 版）→ 收益模拟器回归 → `openspec validate --strict` → `nvcc -arch=sm_86` 编译 CUDA（仅编译）。GPU 实测步骤在 CI 中恒为 `NOT_RUN` 并显式输出。

### D7. 构建脚本
`scripts/build_cuda.sh`：优先 `cmake`，否则直接 `nvcc -O3 -arch=sm_86`；允许 `CUDA_HOME` 指向用户空间工具链（如 conda env），并把 nvcc 主机编译器兼容性问题（gcc 版本上限）记录在文档排错篇。

## Risks / Trade-offs

- [gcc 15 与 nvcc 主机编译器兼容] → conda 用户空间 gcc14；文档记录 `--allow-unsupported-compiler` 备选。
- [驱动 JIT 与 pip-only ptxas 差异] → 使用完整 nvcc 而非 NVRTC，产物为真实 sm_86 cubin。
- [教学目标易挖导致"成功"过于平凡] → easy/medium/genesis 三档分离"能看懂"与"体会难度"，genesis 档在文档中明确说明现代 GPU 无法在课堂时间内挖出真实区块。
- [GPU 被其他进程占用导致 benchmark 抖动] → 报告记录 `nvidia-smi` 快照与多次采样的均值/标准差。
