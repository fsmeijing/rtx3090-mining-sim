# 12. 常见错误排查

## A. 运行类

### 1. `ModuleNotFoundError: No module named 'bitcoin_pow'`

原因：不在仓库根目录运行。
解决：`cd rtx3090-mining-sim` 后再执行 `python3 -m bitcoin_pow ...`。

### 2. `GPU_STATUS: NOT_RUN（找不到 CUDA 可执行程序 …）`

这不是错误——程序如实告诉你"没有 GPU 结果，也不会编造一个"。
想启用 GPU：先编译（见下节），再运行时加 `--gpu`。

### 3. GPU 运行后 `CPU 复核 : FAIL`

含义：GPU 返回的结果与 CPU 独立计算不一致。
按设计这会让程序以非零码退出（绝不允许 GPU 自说自话）。
历史上本项目真实踩过并修复过两类字节序 bug：

- Nonce 写入区块头时忘了 `bswap32`（协议小端 vs 数值序）；
- 摘要与目标逐字比较时忘了 SHA 字到整数大端字节的反转。

如果你自己改动了内核，重点检查这两处；对照创世 Nonce 2,083,236,893
能否被复现是最快的检验。

## B. 编译类（CUDA）

### 4. `错误：未找到 nvcc`

系统没装 CUDA Toolkit。两个选择：

- 系统级安装（需要 sudo，超出本项目范围）；
- 用户空间 conda 工具链（本项目实际使用的方案，无需 sudo）：

```bash
conda create -p /tmp/cuda-env -c nvidia -c conda-forge \
    cuda-nvcc=13.0 cuda-cudart-dev=13.0 gcc_linux-64=14 gxx_linux-64=14
CUDA_HOME=/tmp/cuda-env scripts/build_cuda.sh
```

### 5. `unsupported GNU version! gcc 15.x and later compilers are not supported!`

nvcc 对主机 gcc 版本有上限。方案（任选）：

- 用上面的 conda gcc 14 工具链（推荐）；
- 或加 `-allow-unsupported-compiler`（教学代码通常没问题，但自担风险）。

### 6. `no CUDA-capable device is detected` / `无可用 CUDA 设备`

驱动没装好，或笔记本 NVIDIA 卡没启用。检查 `nvidia-smi` 是否能出表。
编译成功 ≠ 能跑：**编译通过不等于 GPU 实测通过**，两者必须分开报告。

## C. 结果理解类

### 7. 为什么每次 easy 模式结果一模一样？

因为一切都确定：固定题面（创世头）+ 固定起点（Nonce 0）+ 固定目标。
要"体验运气"，换 `--start-nonce` 或换模式。

### 8. 为什么 easy 命中的哈希前导零只有 8 个？

easy 的目标被放大了 2^24 倍，及格线变"松"。目标大 = 及格线高 = 容易。
看 docs/07 和 docs/08 的方向辨析。

### 9. 报告里 MEASURED / THEORETICAL / TEACHING_SIM 什么区别？

| 标签 | 含义 | 例子 |
|---|---|---|
| MEASURED | 本次真实执行测得 | GPU 3.66 GH/s |
| THEORETICAL | 公式推算，仅供参考 | 17.8 TH/s 上界 |
| TEACHING_SIM | 教学参数，与真实硬件无关 | 旧模拟器的 120 MH/s ETHash |

任何实测数字都应该能被你在自己机器上复现；不能复现的"实测"就是假的。

### 10. 测试失败说 height N 复算不一致？

说明区块头字段、字节序或哈希实现被改动了。恢复检查顺序：
`git status` 看改动 → 重跑 `python3 -m bitcoin_pow --verify` →
对照 `docs/blocks-0-19-table.md` 的真实值定位差异字段。

## D. 仍然卡住？

- 先跑 `python3 -m unittest discover -v`，把失败用例编号与
  README/本页对照；
- 在 GitHub 仓库开 Issue，附上：完整命令、完整输出、
  `nvidia-smi` 输出（GPU 相关时）、Python 版本。
