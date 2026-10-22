# pow-target 规格

## ADDED Requirements

### Requirement: nBits 目标解码
实现 SHALL 将 4 字节压缩 nBits（exponent + 3 字节 mantissa）解码为完整 256-bit 目标整数 T = mantissa × 256^(exponent−3)，SHALL 支持 nBits=0x1d00ffff（创世目标），且 SHALL 对非规范 mantissa（最高字节 ≥ 0x80）给出警告标记。

#### Scenario: 创世 nBits 解码
- **WHEN** 解码 nBits = 0x1d00ffff
- **THEN** 得到目标 `0x00000000FFFF0000000000000000000000000000000000000000000000000000`

### Requirement: 完整 256-bit 整数比较
实现 SHALL 使用完整 256-bit 无符号整数比较判断 H ≤ T，SHALL 禁止任何"只比较前缀/前导零"的捷径实现，并 SHALL 提供边界用例覆盖 H == T、H = T+1、H = T−1。

#### Scenario: 相等边界
- **WHEN** H 的整数值恰好等于 T
- **THEN** 判定为满足工作量证明（H ≤ T 成立）

#### Scenario: 差一越界
- **WHEN** H = T + 1（十六进制展示仅末位差 1）
- **THEN** 判定为不满足；且 H = T − 1 判定为满足

### Requirement: 教学难度模式
CLI SHALL 提供三种模式：`--mode easy`（创世目标左移 24 位，命中概率提高约 2^24 倍）、`--mode medium`（左移 12 位）、`--mode genesis`（原始创世目标），且 SHALL 在输出中明确打印当前模式的目标 T（完整 64 位十六进制）与命中难度说明。

#### Scenario: 模式切换改变目标
- **WHEN** 分别以 easy、medium、genesis 模式打印目标
- **THEN** 三者目标整数大小（即命中概率）满足 easy > medium > genesis，目标自身前导零比特数满足反序，且 genesis 目标等于 nBits=0x1d00ffff 解码值
