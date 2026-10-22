# block-header-codec 规格

## ADDED Requirements

### Requirement: 80 字节区块头序列化
CPU 参考实现 SHALL 提供函数，把 6 个字段（Version、PrevHash、MerkleRoot、Timestamp、nBits、Nonce）序列化为精确 80 字节的区块头，且字段顺序与比特币协议一致（Version 4B、PrevHash 32B、MerkleRoot 32B、Timestamp 4B、nBits 4B、Nonce 4B，均按协议小端序写入）。

#### Scenario: 创世区块头长度与内容
- **WHEN** 用创世区块六字段数据调用序列化函数
- **THEN** 返回值长度为 80 字节，且十六进制表示以 `01000000` 开头、以创世 Nonce `2083236893`（小端 `e9614f7d`）结尾

### Requirement: 字段字节序与展示
实现 SHALL 在内部使用协议字节序（小端存储），对外 SHALL 同时提供大端十六进制展示（与区块浏览器一致），且 SHALL 明确标注所使用的字节序。

#### Scenario: MerkleRoot 双向转换
- **WHEN** 将创世 MerkleRoot 大端展示串 `4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b` 转换为协议字节序再转回
- **THEN** 两次转换结果与输入完全一致（往返恒等）

### Requirement: Nonce 修改产生确定性区块头
实现 SHALL 支持"输入区块头 + 新 Nonce → 输出新区块头"，且除 Nonce 字段外其余 76 字节 SHALL 保持不变。

#### Scenario: 仅 Nonce 字段变化
- **WHEN** 对创世区块头分别使用 Nonce=0 与 Nonce=2083236893 序列化
- **THEN** 两个区块头仅最后 4 字节不同，前 76 字节逐字节相同
