# cuda-mining-simulation 规格

## ADDED Requirements

### Requirement: CUDA C++17 并行 Nonce 搜索
项目 SHALL 提供 CUDA C++17 内核，在 RTX 3090（sm_86）上并行搜索 Nonce：每线程从分配的 Nonce 子区间取值、在 GPU 上完成双重 SHA-256 并与目标 T 做完整 256-bit 比较；内核 SHALL 在命中后通过原子操作写回（Nonce, 256-bit 哈希）。

#### Scenario: GPU 结果与 CPU 一致
- **WHEN** 在 easy 模式下运行 GPU 搜索并得到成功 Nonce
- **THEN** CPU 参考实现用相同区块头与该 Nonce 复算，得到的哈希与 GPU 报告值逐字节一致

### Requirement: CLI 运行模式
GPU 可执行程序与 Python 统一入口 SHALL 支持：`--verify`（创世区块验证）、`--mode easy|medium|genesis`、`--benchmark`（固定工作量测速）、`--seconds N`（运行时长上限）、`--max-attempts N`（尝试次数上限）。

#### Scenario: verify 模式
- **WHEN** 执行 `--verify`
- **THEN** 程序输出创世区块头六字段、完整哈希 H，与已知创世哈希比对结果为 MATCH

#### Scenario: 安全上限生效
- **WHEN** 在 genesis 模式下设置 `--max-attempts 1000000`
- **THEN** 程序在累计尝试达到上限后停止，输出已达上限状态，且不产生未经验证的"成功"

### Requirement: 安全运行边界
GPU 程序 SHALL 强制设置每轮 kernel launch 的每线程迭代上限，且 `--seconds` 与 `--max-attempts` SHALL 在 CPU 侧循环调度中生效，保证程序可在有限时间内退出。

#### Scenario: seconds 上限
- **WHEN** 以 `--mode medium --seconds 5` 运行且未找到解
- **THEN** 程序运行时间接近并不超过明显超出（≥ 5s 且 < 15s）后正常退出，并如实报告未找到解

### Requirement: CPU 复核门禁
GPU 报告的任何成功结果 SHALL 在 CPU 复核通过后才输出为最终成功；复核失败时程序 SHALL 报告错误并以非零退出码结束。

#### Scenario: 复核失败即失败
- **WHEN** 模拟一个 GPU 返回错误哈希的场景（注入测试）
- **THEN** CPU 复核判定不一致，程序报告 `CPU_RECHECK: FAIL` 并以非零退出码结束
