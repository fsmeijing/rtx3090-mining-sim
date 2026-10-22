cmake_minimum_required(VERSION 3.24)
project(rt3090_sha256d_miner LANGUAGES CUDA CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)

# 目标硬件：NVIDIA RTX 3090（Ampere，sm_86）
if(NOT CMAKE_CUDA_ARCHITECTURES)
    set(CMAKE_CUDA_ARCHITECTURES 86)
endif()

add_executable(sha256d_miner main.cu)
set_target_properties(sha256d_miner PROPERTIES
    CUDA_SEPARABLE_COMPILATION OFF)
target_compile_options(sha256d_miner PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:-O3 --use_fast_math -Xptxas -O3>)
