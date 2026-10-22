# benchmark-reporting 规格

## ADDED Requirements

### Requirement: 算力测量输出项
`--benchmark` SHALL 输出：GPU 型号、CUDA 版本、驱动版本、Nonce 搜索范围、累计尝试次数、运行时间、GPU H/s 及其换算（H/s、MH/s、GH/s）、成功哈希 H、难度目标 T、CPU 复核结果。

#### Scenario: 完整报告字段
- **WHEN** 在有 GPU 的机器上以 easy 模式运行 benchmark 并导出 JSON
- **THEN** JSON 包含上述全部字段且数值类型正确，H/s > 0，总尝试次数 = 各轮 launch 次数 × 每轮线程数 × 每线程迭代数

### Requirement: 数据来源标签
报告中每个数值 SHALL 标注来源：`MEASURED`（真实测量）、`THEORETICAL`（理论推算，须给出推算依据）、`TEACHING_SIM`（教学模拟）。项目 SHALL 禁止将任何虚构或估算数值标注为实测。

#### Scenario: 无 GPU 时明确标记
- **WHEN** 在没有 GPU 的环境运行 benchmark 入口
- **THEN** 输出 `GPU_STATUS: NOT_RUN`，不输出任何伪实测数值，退出码为 0（如实标记而非报错）

#### Scenario: 理论值不得冒充实测
- **WHEN** 报告中出现理论推算的算力数值（如按 SM 数 × 频率推算）
- **THEN** 该数值标签为 `THEORETICAL` 并附推算公式，与 `MEASURED` 数值并列区分

### Requirement: 复现性
benchmark SHALL 支持 `--seed` 与固定的每轮 Nonce 起点，使相同命令在相同环境下可复现累计尝试次数与命中结果。

#### Scenario: 同种子复现
- **WHEN** 两次以相同参数与 `--seed` 运行 easy 模式 benchmark
- **THEN** 两次的 Nonce 搜索起点、命中 Nonce 与成功哈希完全一致（仅用时与 H/s 允许波动）
