# benchmark-reporting 规格

## ADDED Requirements

### Requirement: 算力测量输出项
`--benchmark` SHALL 输出：GPU 型号、CUDA 版本、驱动版本、Nonce 搜索范围、累计尝试次数、运行时间、GPU H/s 及其换算（H/s、MH/s、GH/s）、成功哈希 H、难度目标 T、CPU 复核结果。

#### Scenario: 完整报告字段
- **WHEN** 在有 GPU 的机器上以 easy 模式运行 benchmark 并导出 JSON
- **THEN** JSON 包含上述全部字段且数值类型正确，H/s > 0，总尝试次数与 completed_hashes 分离报告

### Requirement: 数据来源标签
报告中每个数值 SHALL 标注来源：`MEASURED`（真实测量）、`THEORETICAL`（理论推算，须给出推算依据）、`TEACHING_SIM`（教学模拟）。项目 SHALL 禁止将任何虚构或估算数值标注为实测。

#### Scenario: 无 GPU 时明确标记
- **WHEN** 在没有 GPU 的环境运行 benchmark 入口
- **THEN** 输出 `GPU_STATUS: NOT_RUN`，不输出任何伪实测数值，退出码为 0（如实标记而非报错）

#### Scenario: 理论值不得冒充实测
- **WHEN** 报告中出现理论推算数值
- **THEN** 该数值标签为 `THEORETICAL` 并附推算公式，且只覆盖有可靠模型的量

#### Scenario: 无可靠模型不报告理论 SHA-256d 算力
- **WHEN** 生成理论吞吐量分层说明
- **THEN** 报告区分"32-bit 整数操作吞吐量"（规格推算）、"SHA-256 压缩吞吐量"（绝对上界量级并注明不可达）、"SHA-256d 哈希吞吐量"；第三层在无可靠模型时 SHALL 输出 null 而非编造数字，且不得把整数操作吞吐量当作 SHA-256d 上界与实测值做倍数比较

### Requirement: 诚实统计契约
算力统计 SHALL 区分 `scheduled_attempts`（已分配工作量）与 `completed_hashes`（内核实际完成哈希数，atomicAdd 累计）；`hash_rate` SHALL 等于 `completed_hashes / elapsed_seconds`；因命中而提前退出的线程工作量 SHALL 只计入 scheduled，SHALL 禁止把分配量冒充完成量。

#### Scenario: 提前退出不虚报算力
- **WHEN** 搜索模式命中后同一 launch 内剩余线程提前退出
- **THEN** completed_hashes 严格小于 scheduled_attempts，差值如实保留，hash_rate 只基于 completed_hashes 计算

### Requirement: 固定工作量 Benchmark
`--benchmark` 的 GPU 吞吐口径 SHALL 使用 fixed-work 模式：不做 H<=T 判定、不因命中提前退出、使用由 `--start-nonce` 与轮数预先确定的 Nonce 范围、在 32-bit Nonce 上界处正确截断、遵守运行时间上限、报告实际完成哈希数量，并 SHALL 重复多次运行统计吞吐量（min/median/max）。

#### Scenario: 固定工作量统计
- **WHEN** 运行固定工作量 benchmark（默认 3 次、每次 20 轮）
- **THEN** 每次运行 scheduled_attempts == completed_hashes（无提前退出），报告输出 min/median/max 吞吐量与累计 completed_hashes

### Requirement: 复现性
benchmark SHALL 支持 `--seed` 与固定的每轮 Nonce 起点，使相同命令在相同环境下可复现累计尝试次数与命中结果。

#### Scenario: 同种子复现
- **WHEN** 两次以相同参数与 `--seed` 运行 easy 模式 benchmark
- **THEN** 两次的 Nonce 搜索起点、命中 Nonce 与成功哈希完全一致（仅用时与 H/s 允许波动）
