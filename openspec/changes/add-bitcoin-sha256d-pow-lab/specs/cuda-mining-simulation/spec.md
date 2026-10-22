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

### Requirement: 精确计算预算（窗口式分配）
搜索模式 SHALL 保证实际执行的 SHA-256d 计算次数不超过用户设置的 max-attempts：Host 端 SHALL 为每轮 launch 确定精确 Nonce 窗口 `[window_start, window_end)`（上界 = min(剩余预算, 2^32, GPU 单轮覆盖)），窗口上界 SHALL 传入 Kernel，Kernel 中 nonce >= window_end 的迭代 SHALL 不执行任何 SHA-256d；窗口末端不足一个 block 的任务 SHALL 正确处理（部分线程休眠），同时 SHALL 保留并行执行能力与命中提前退出。必须区分 `scheduled_attempts`（有效分配的候选 Nonce 数量）与 `completed_hashes`（实际完成 SHA-256d 数），且不变式 `completed <= scheduled <= max_attempts` SHALL 恒成立；SHALL 禁止通过修改输出统计值掩盖实际超量计算。

#### Scenario: max-attempts=1 精确执行
- **WHEN** search 模式设置 `--max-attempts 1`（threads_per_block=256、iters=64）
- **THEN** scheduled_attempts = 1 且 completed_hashes = 1（旧实现会分配 16384）

#### Scenario: 非整块预算
- **WHEN** 分别设置 `--max-attempts` 为 16383、16384、16385（目标设为不可能命中的全零）
- **THEN** 三种情况 scheduled_attempts 与 completed_hashes 均精确等于预算值，无整块超额分配

#### Scenario: 提前命中不超出预算
- **WHEN** 搜索在窗口内提前命中
- **THEN** completed_hashes <= scheduled_attempts，差值（命中后休眠线程）如实保留

#### Scenario: 输出字段内部一致
- **WHEN** 检查任意一次执行的 JSON 输出
- **THEN** `end_nonce - start_nonce == scheduled_attempts`、`hash_rate == completed/elapsed`、`max_attempts_budget` 与输入一致、status/reason 与 found 一致

### Requirement: fixed-work 严格预算
fixed-work 模式 SHALL 严格受 `--max-attempts`（每次运行的预算，非多次运行共享总额）、`--rounds`、`--seconds` 三重限制：最后一轮 Kernel SHALL 根据剩余预算与 32-bit Nonce 上界截断；Benchmark SHALL 不执行难度命中提前退出；每轮有效执行的哈希 SHALL 全部计入 completed_hashes；JSON 的 reason SHALL 记录最早触发的结束条件（同刻触发按 time-limit > rounds-done > max-attempts 顺序判定）；Python CLI SHALL 向 CUDA 程序正确传递预算参数，SHALL 禁止静默忽略用户输入。

#### Scenario: fixed-work 精确预算
- **WHEN** fixed-work 模式分别设置 `--max-attempts` 为 1、1000、16385
- **THEN** scheduled_attempts 与 completed_hashes 均恰好等于预算值

#### Scenario: 预算先于轮数耗尽
- **WHEN** fixed-work 设置 `--max-attempts 100000` 且轮数充足
- **THEN** reason = max-attempts，completed = 100000

#### Scenario: 轮数先于预算耗尽
- **WHEN** fixed-work 设置 `--rounds 3` 且预算充足
- **THEN** reason = rounds-done，rounds = 3

#### Scenario: 多次运行的预算语义
- **WHEN** benchmark 重复多次运行并在 CLI/JSON/OpenSpec/文档中描述预算
- **THEN** max-attempts 明确标注为"每次运行的预算"（各次独立享有，非共享总额），JSON 中以 `max_attempts_budget.per_run` 记录，各次运行的 reason 逐次保留

### Requirement: GPU 状态四态枚举
CLI 与 Python GPURunner SHALL 以四态区分 GPU 执行结果：`GPU_NOT_RUN`（未执行）、`GPU_ERROR`（参数错误/CUDA 错误）、`GPU_RUN_NO_HIT`（正常执行未命中）、`GPU_RUN_FOUND`（正常执行命中）。CUDA 可执行程序退出码契约 SHALL 为：0=正常执行（含未命中）、2=参数错误、3=CUDA 执行错误。正常执行但未命中时 SHALL 保留 attempts/elapsed/hash_rate 等统计且绝不标记 NOT_RUN。

#### Scenario: 正常执行但未命中
- **WHEN** GPU 正常完成搜索但在上限内未找到满足 H<=T 的 Nonce
- **THEN** 输出 `GPU_STATUS` 为 RUN（状态枚举 `GPU_RUN_NO_HIT`）、`found=false`、统计数据完整保留，不出现 NOT_RUN，退出码为 0

#### Scenario: CUDA 执行错误
- **WHEN** CUDA API/内核启动/同步返回错误（退出码 3）
- **THEN** CLI 输出 `GPU_STATUS: ERROR` 与原因，不产出任何可信数值，以非零退出码结束

### Requirement: 参数与 Nonce 边界防御
CUDA 程序 SHALL 校验：`--seconds` 必须为正且有限、`--max-attempts` 必须 >= 1、`--start-nonce` 必须在 [0, 2^32)、必需参数缺失即拒绝；Nonce 搜索 SHALL 在 32-bit 空间上界处正确截断，空间耗尽时 SHALL 如实报告而非挂起；所有 CUDA API 调用与内核启动 SHALL 检查返回码。

#### Scenario: 非法参数拒绝
- **WHEN** 传入 `--seconds 0`、`--seconds abc`、`--max-attempts 0` 或缺失 `--header-hex`
- **THEN** 程序以退出码 2 拒绝执行并给出参数错误说明

#### Scenario: start-nonce 超界
- **WHEN** 传入 `--start-nonce 4294967296`（>= 2^32）
- **THEN** 程序以退出码 2 拒绝执行

#### Scenario: Nonce 空间耗尽
- **WHEN** 搜索从接近 2^32 的起点开始直至空间耗尽且未命中
- **THEN** 程序正常退出，状态为 `GPU_RUN_NO_HIT`，reason 为 nonce-space-exhausted，completed_hashes 只计实际完成量

#### Scenario: 尾部单个 Nonce 边界
- **WHEN** `--start-nonce 4294967295`（最后一个 Nonce）且目标为必然命中值
- **THEN** 程序最多计算 1 个 Nonce（completed_hashes <= 1）并命中该 Nonce
