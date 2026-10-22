# sha256d-reference 规格

## ADDED Requirements

### Requirement: 双重 SHA-256 参考实现
CPU 参考实现 SHALL 提供 SHA256d 函数 H = SHA256(SHA256(x))，基于 Python 标准库 hashlib，且 SHALL 对任意输入返回 32 字节摘要。

#### Scenario: SHA-256 标准测试向量
- **WHEN** 对 ASCII 空串 `"abc"` 分别计算单次 SHA-256 与 SHA256d
- **THEN** 单次结果为 `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`，且 SHA256d 结果与 OpenSSL 逐级计算一致

### Requirement: 创世区块复算
实现 SHALL 使用真实创世区块数据（Version=1、PrevHash=全零、MerkleRoot=4a5e…a33b、Timestamp=1231006505、nBits=0x1d00ffff、Nonce=2083236893）复算区块头哈希。

#### Scenario: 创世区块哈希完全一致
- **WHEN** 序列化创世区块头并计算 SHA256d
- **THEN** 结果等于 `000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f`，并完整输出全部 64 个十六进制字符

### Requirement: 高度 0–19 真实区块测试向量
项目 SHALL 内置比特币主网高度 0–19 共 20 个区块的（Version、PrevHash、MerkleRoot、Timestamp、nBits、Nonce、预期哈希）测试向量，以 JSON 数据文件与 Markdown 对照表两种形式提交。

#### Scenario: 高度 0–19 全部复算通过
- **WHEN** 对 20 个区块逐一生成 80 字节区块头并计算 SHA256d
- **THEN** 20 个哈希与内置预期值全部一致，测试无失败

### Requirement: CPU 独立复核 GPU 结果
所有 GPU 声称的成功结果 SHALL 能由 CPU 参考实现独立复核：给定 GPU 返回的 Nonce，CPU SHALL 能重建区块头、计算 SHA256d 并比对目标。

#### Scenario: GPU Nonce 的 CPU 复核
- **WHEN** GPU 返回一个满足目标的 Nonce
- **THEN** CPU 用同一区块头与该 Nonce 复算 SHA256d，得到与 GPU 相同的 256-bit 哈希，且 H ≤ T 成立
