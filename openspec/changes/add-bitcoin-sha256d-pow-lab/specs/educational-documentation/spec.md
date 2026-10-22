# educational-documentation 规格

## ADDED Requirements

### Requirement: 教学文档主题覆盖
`docs/` SHALL 以 Markdown 提供至少以下主题的中文教学文档：区块与区块头、SHA-256 工作原理、Nonce 与 ExtraNonce、创世区块、区块 #1 的产生、Merkle Root、nBits 与难度目标、H 与 T 的整数比较、CPU 与 GPU 的计算差异、RTX 3090 算力测试、实验操作指南、常见错误排查。

#### Scenario: 文档完整性检查
- **WHEN** 列出 docs/ 目录
- **THEN** 上述 12 个主题均有对应文档文件，且每篇包含目录级标题与至少一个来自本项目的真实命令或真实数据示例

### Requirement: 受众适配
文档 SHALL 面向初中生：语言通俗、术语首次出现时给出解释，同时 SHALL 保持技术准确（示例数据必须来自程序真实输出或真实区块链数据）。

#### Scenario: 示例数据真实性
- **WHEN** 抽取任一文档中的创世哈希、区块头字段或 benchmark 数字
- **THEN** 创世哈希等链上数据与主网一致；benchmark 数字与 reports/ 中真实报告一致，不存在虚构数值

### Requirement: 高度 0–19 对照表
项目 SHALL 提供高度 0–19 区块的 Markdown 对照表（高度、Version、Timestamp、nBits、Nonce、哈希），数据与 JSON 测试向量同源。

#### Scenario: 对照表与测试向量一致
- **WHEN** 对照测试向量 JSON 与 Markdown 对照表
- **THEN** 20 个区块的字段值逐项一致
