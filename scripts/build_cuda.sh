#!/usr/bin/env bash
# 编译 CUDA SHA-256d 挖矿教学程序（RTX 3090, sm_86）。
#
# 优先使用 cmake；不可用时直接调用 nvcc。
# 支持用户空间工具链：设置 CUDA_HOME（如 conda env 前缀）或 PATH 中的 nvcc。
#
# 用法：
#   scripts/build_cuda.sh                  # 默认输出 cuda/build/sha256d_miner
#   CUDA_HOME=/path/to/env scripts/build_cuda.sh
#   CUDA_HOME=/path/to/env CXX=/path/to/g++ scripts/build_cuda.sh
#   SKIP_CMAKE=1 scripts/build_cuda.sh     # 跳过 cmake，直接 nvcc
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CUDA_DIR="$REPO/cuda"
BUILD_DIR="$CUDA_DIR/build"
ARCH="${CUDA_ARCH:-86}"

mkdir -p "$BUILD_DIR"

# 定位 nvcc：CUDA_HOME/bin/nvcc 优先，其次 PATH。
if [[ -n "${CUDA_HOME:-}" && -x "$CUDA_HOME/bin/nvcc" ]]; then
    NVCC="$CUDA_HOME/bin/nvcc"
elif command -v nvcc >/dev/null 2>&1; then
    NVCC="$(command -v nvcc)"
else
    echo "错误：未找到 nvcc。请安装 CUDA Toolkit 或设置 CUDA_HOME。" >&2
    echo "提示：本仓库开发使用用户空间 conda 工具链（无需 sudo）：" >&2
    echo "  conda create -p /tmp/cuda-env -c nvidia -c conda-forge cuda-nvcc=13.0 cuda-cudart-dev=13.0 gcc_linux-64=14 gxx_linux-64=14" >&2
    exit 1
fi
echo "使用编译器: $NVCC"
"$NVCC" --version | tail -1

echo "== 构建 sha256d_miner (sm_$ARCH) =="
if command -v cmake >/dev/null 2>&1 && [[ -z "${SKIP_CMAKE:-}" ]]; then
    # CMake 路径：仅在显式提供时传递编译器参数，绝不传空字符串参数。
    CMAKE_ARGS=(-S "$CUDA_DIR" -B "$BUILD_DIR/cmake"
                -DCMAKE_CUDA_ARCHITECTURES="$ARCH"
                -DCMAKE_BUILD_TYPE=Release)
    if [[ -n "${CUDA_HOME:-}" ]]; then
        CMAKE_ARGS+=(-DCMAKE_CUDA_COMPILER="$NVCC")
        if [[ -n "${CXX:-}" ]]; then
            CMAKE_ARGS+=(-DCMAKE_CUDA_HOST_COMPILER="$CXX"
                         -DCMAKE_CXX_COMPILER="$CXX")
        fi
    fi
    cmake "${CMAKE_ARGS[@]}"
    cmake --build "$BUILD_DIR/cmake" -j
    cp "$BUILD_DIR/cmake/sha256d_miner" "$BUILD_DIR/sha256d_miner"
else
    # nvcc 直编路径。
    # 主机编译器：仅在有明确值时传 -ccbin，绝不传空。
    HOST_CXX=()
    if [[ -n "${CXX:-}" ]]; then
        HOST_CXX=(-ccbin "$CXX")
    elif [[ -n "${CUDA_HOME:-}" && -x "$CUDA_HOME/bin/x86_64-conda-linux-gnu-g++" ]]; then
        HOST_CXX=(-ccbin "$CUDA_HOME/bin/x86_64-conda-linux-gnu-g++")
    fi
    "$NVCC" -O3 -std=c++17 -arch="sm_$ARCH" \
        "${HOST_CXX[@]}" \
        -o "$BUILD_DIR/sha256d_miner" "$CUDA_DIR/main.cu"
fi

echo "== 构建完成: $BUILD_DIR/sha256d_miner =="
