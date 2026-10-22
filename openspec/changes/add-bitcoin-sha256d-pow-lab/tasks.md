# Tasks: add-bitcoin-sha256d-pow-lab

## 1. OpenSpec 与基线
- [x] 1.1 审计仓库：Git 状态、remote、现有代码与测试基线（7 个测试通过）
- [x] 1.2 初始化 OpenSpec（--tools opencode --language zh-CN）
- [x] 1.3 编写 proposal.md / design.md / specs（7 个 capability）/ tasks.md
- [x] 1.4 `openspec validate add-bitcoin-sha256d-pow-lab --strict` 通过

## 2. 阶段 A：CPU 参考实现
- [x] 2.1 实现 `bitcoin_pow/block_header.py`：80 字节序列化、字节序转换、Nonce 修改
- [x] 2.2 实现 `bitcoin_pow/sha256d.py`：SHA256d 与标准测试向量
- [x] 2.3 实现 `bitcoin_pow/target.py`：nBits 解码、完整 256-bit 比较、教学难度模式
- [x] 2.4 实现 `bitcoin_pow/genesis.py` 与 `--verify`：创世区块复算
- [x] 2.5 采集高度 0–19 真实区块数据 → `bitcoin_pow/data/blocks_0_19.json` + `docs/blocks-0-19-table.md`
- [x] 2.6 单元测试：序列化/SHA256d/nBits 边界/创世复算/0–19 向量
- [x] 2.7 原有收益模拟器回归测试通过

## 3. 阶段 B：CUDA GPU 实现
- [x] 3.1 `cuda/sha256d.cu`：寄存器内联双 SHA-256 内核 + 原子写回
- [x] 3.2 主机侧：网格配置（82 SM×16×256）、安全上限、结果回传
- [x] 3.3 Python 统一入口 `bitcoin_pow/cli.py`：--verify/--mode/--benchmark/--seconds/--max-attempts
- [x] 3.4 `cuda/CMakeLists.txt` 与 `scripts/build_cuda.sh`（sm_86）
- [x] 3.5 真机编译（CUDA 13.0 + RTX 3090）并运行 --verify；genesis 模式复现真实创世 Nonce

## 4. 阶段 C：真实算力统计
- [x] 4.1 benchmark JSON/Markdown 报告生成（来源标签 MEASURED/THEORETICAL/TEACHING_SIM）
- [x] 4.2 RTX 3090 实测 easy/medium/genesis 模式 H/s，报告写入 `reports/`
- [x] 4.3 CPU 复核 GPU 命中结果（含注入失败用例测试）

## 5. 阶段 D：教学文档
- [x] 5.1 撰写 12 篇教学文档（区块头/SHA-256/Nonce/创世/区块#1/Merkle/nBits/比较/CPU-GPU/算力实测/操作指南/排错）
- [x] 5.2 更新 README（区分收益模拟与 PoW 实验，保留原内容）

## 6. 阶段 E：CI 与交付
- [x] 6.1 `.github/workflows/ci.yml`：CPU 测试 + 创世验证 + 向量 + nBits + Nonce 正确性 + 回归 + openspec 严格验证 + CUDA 编译门禁（GPU 实测 NOT_RUN）
- [x] 6.2 推送 `feat/bitcoin-sha256d-pow-lab`，创建 PR，CI 全绿
- [x] 6.3 汇总验收清单与最终报告

## 7. PR #1 审查修复
- [x] 7.1 GPU 状态四态枚举（NOT_RUN/ERROR/RUN_NO_HIT/RUN_FOUND）与退出码契约（0/2/3）
- [x] 7.2 scheduled_attempts 与 completed_hashes 分离，hash_rate 只基于 completed
- [x] 7.3 固定工作量 Benchmark（无提前退出/预设 Nonce 范围/32-bit 截断/时间上限/多次运行统计）
- [x] 7.4 删除错误理论 SHA-256d 上界，理论吞吐量三层分解（SHA-256d 层报告 null）
- [x] 7.5 边界防御：CUDA API 返回码/内核启动错误/非法参数/start-nonce 超界/Nonce 空间耗尽/参数缺失
- [x] 7.6 diff_int() 字节序修复（与 compare() 小端语义一致）+ 回归测试
- [x] 7.7 构建清理：CMake 无 CUDA_HOME/CXX 行为修复、git rm --cached 二进制
- [x] 7.8 RTX 3090 复测：genesis 复核 PASS、固定工作量 benchmark（median 3.74 GH/s genesis / 3.53 GH/s medium）
- [x] 7.9 文档与报告同步勘误（docs/09、docs/10、reports/、README）
