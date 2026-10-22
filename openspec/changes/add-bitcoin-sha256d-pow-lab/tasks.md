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

## 8. PR #1 预算边界修复（最终）
- [x] 8.1 问题 A：search 模式精确预算 —— Host 端窗口 [start, min(剩余预算, 2^32, GPU覆盖))，window_end 传入 Kernel，窗口外不执行 SHA-256d，尾部不足一个 block 正确处理
- [x] 8.2 不变式 completed <= scheduled <= max_attempts 恒成立；禁止改统计值掩盖超算
- [x] 8.3 问题 B：fixed-work 严格 max-attempts（每次运行预算语义）；rounds/seconds/预算三限，reason 记录最早触发者（time-limit > rounds-done > max-attempts）
- [x] 8.4 Python CLI 传递预算参数；JSON 增 max_attempts_budget（per_run + semantics）
- [x] 8.5 新增 tests/test_budget_contract.py（18 项：search 1/1000/16383/16384/16385、fixed-work 1/1000/16385、尾部 Nonce、提前命中、时间限制、三限优先级、参数拒绝、内部一致性；无 GPU 环境显式 SKIP）
- [x] 8.6 RTX 3090 实测：预算边界逐项验证 + genesis 复算（CPU MATCH / GPU 复现真实 Nonce）+ fixed-work benchmark 3 次
- [x] 8.7 文档/README/reports 同步 per-run 语义与新实测数据

## 9. PR #1 预算参数传递与正确性门禁修复（最终审查）
- [x] 9.1 benchmark.py fixed-work mine() 传递用户实际预算（修复硬编码 1 << 40 遗漏）
- [x] 9.2 max_attempts_budget.per_run 与逐次 max_attempts_budget_per_run 一致（effective_budget = min(用户, 2^40)，JSON 增加 requested 字段）
- [x] 9.3 正确性门禁：PASS 当且仅当 GPU found=true 且 CPU 复核通过；未命中 NOT_VERIFIED（不伪造 PASS）；复核不一致 FAIL；检查阶段独立预算（1<<32）在 JSON 中明确标注与测速预算区分
- [x] 9.4 新增 tests/test_benchmark_budget.py（9 项：传参捕获回归、默认预算透传、独立预算区分、门禁三分支、真机 1/1000/16385）
- [x] 9.5 RTX 3090 实测：--benchmark --gpu --max-attempts 1/1000/16385，每次 fixed-work 完成数 <= 预算
