# 5. 区块 #1 的产生

## 创世之后的第一块

创世区块挖出后 **6 天**（2009-01-09），中本聪挖出了高度 1 的区块。
前 20 个区块的数据我们已内置为测试向量（见 docs/blocks-0-19-table.md）：

| 项 | 值 |
|---|---|
| 高度 | 1 |
| PrevHash | `000000000019d668...8ce26f`（创世哈希，链条扣上了！） |
| MerkleRoot | `0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098` |
| Timestamp | 1231469665 |
| nBits | 0x1d00ffff（仍是难度 1） |
| Nonce | 2,573,394,689 |
| 哈希 | `00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048` |

## "产生一个区块"到底发生了什么？

1. 矿工收集交易，算出默克尔根，填进区块头；
2. 把上一块哈希填进 PrevHash——从此这条链"接"上了；
3. 不停换 Nonce 算双重 SHA-256；
4. 直到某个 Nonce 让 H ≤ T，把区块广播给全网；
5. 其他节点**只需一次哈希运算**就能验证："哈希确实 ≤ 目标，收下！"

注意不对等的 labor：**找 Nonce 要试几百万次，验证只要算一次**。
这正是工作量证明（Proof-of-Work）的精髓——制造稀缺，而非制造保密。

## 本项目的"区块 #1 复刻"玩法

区块 #1 的所有字段都内置在测试向量里，你可以让它成为挖矿题面：

```python
from bitcoin_pow.block_header import BlockHeader
from bitcoin_pow.genesis import search_nonce
from bitcoin_pow.target import mode_target

b1 = BlockHeader(1,
    "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
    "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098",
    1231469665, 0x1d00ffff, 0)
res = search_nonce(b1, mode_target("easy"), start_nonce=0, max_attempts=1_000_000)
print(res.found, res.nonce, res.hash_hex)
```

用 easy 难度挖"区块 #1 题面"，你会得到一个**和历史上不同的** Nonce——
因为目标 T 被放大了 2^24 倍，满足条件的 Nonce 有很多个。
历史上中本聪的那个 Nonce 满足的是**原始**目标（genesis 模式）。

## 高度 0–19 全链验证

```bash
python3 -m unittest tests.test_real_blocks -v
# 20 个真实区块头全部复算通过（CPU 独立验证）
```

