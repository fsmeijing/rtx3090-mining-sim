# offline-safety 规格

## ADDED Requirements

### Requirement: 完全离线
全部代码路径 SHALL 不发起任何网络连接（矿池、比特币 P2P、RPC、HTTP、DNS）， SHALL 不读写钱包文件， SHALL 不处理私钥或真实交易。测试 SHALL 验证核心模块 import 时不引入网络客户端库。

#### Scenario: 静态离线检查
- **WHEN** 对 bitcoin_pow/ 与 cuda/ 全部源码执行网络关键字扫描（socket、urllib、requests、stratum、http 等）
- **THEN** 无任何网络调用代码路径

### Requirement: 旧功能保留
现有收益模拟器（simulator.py、test_simulator.py）SHALL 原样保留且测试不回归；新增模块 SHALL 与旧模块物理隔离（独立包/目录），SHALL 禁止将 ETHash 算力数据（如 120 MH/s）标注为 Bitcoin SHA-256d 算力。

#### Scenario: 回归测试
- **WHEN** 在新增全部模块后运行原 unittest 全量
- **THEN** 原 7 个测试全部通过

### Requirement: 敏感信息与破坏性操作禁止
提交内容 SHALL 不包含凭据、私钥、令牌或本地敏感路径；开发流程 SHALL 禁止直接修改 main、禁止强推、禁止覆盖用户未提交修改。

#### Scenario: 分支与提交检查
- **WHEN** 检查交付分支与提交内容
- **THEN** 工作在 feat/ 分支，提交中无密钥类文件，main 分支历史未被改写
