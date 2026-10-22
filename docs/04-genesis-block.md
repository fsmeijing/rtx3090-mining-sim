# 4. 创世区块

## 第 0 块：一切的起点

2009 年 1 月 3 日 18:15:05（UTC），中本聪挖出了比特币区块链的第一个区块——**创世区块（Genesis Block，高度 0）**。它没有"上一块"，所以 PrevHash 是 64 个 0。

## 它藏着一条报纸标题

创世区块的第一笔交易里写入了当天《泰晤士报》的头版标题：

> The Times 03/Jan/2009 Chancellor on brink of second bailout for banks

这句话像"时间戳印章"：证明创世区块不可能早于 2009-01-03 挖出，
也暗含了比特币的诞生动机——对银行救助体系的不信任。

## 创世区块的六个字段（真实数据）

```
Version    = 1
PrevHash   = 0000000000000000000000000000000000000000000000000000000000000000
MerkleRoot = 4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b
Timestamp  = 1231006505
nBits      = 0x1d00ffff
Nonce      = 2083236893
```

## 它的哈希（本仓库实测复现）

```
000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
```

以 10 个 0 开头 —— 这就是难度目标 `0x1d00ffff` 要求的"足够小"。

## 用本项目复算它

```bash
python3 -m bitcoin_pow --verify
```

输出（节选）：

```
创世区块复算
  计算 H      = 000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
  期望哈希    = 000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
  比对结果    = MATCH
```

`--verify` 只做一件事：把 6 个字段拼成 80 字节、算双重 SHA-256、
和已知答案比对。它不需要网络，也不需要显卡——一台普通电脑即可完成。

## CPU 也能"重演历史"

```bash
# GPU 版（如果有 RTX 3090）：0.6 秒左右重新"挖出"创世区块
python3 -m bitcoin_pow --mode genesis --gpu --seconds 60

# CPU 版：难度太高，可加 --max-attempts 体验"尽力而为"
python3 -m bitcoin_pow --mode genesis --max-attempts 100000000
```

GPU 实测在真实创世难度下 0.64 秒扫描 20.8 亿个 Nonce 后命中
**2,083,236,893** —— 与历史完全一致（详见 docs/10）。
