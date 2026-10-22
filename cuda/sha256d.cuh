// sha256d.cuh — 比特币双重 SHA-256 CUDA 内核（教学用途，完全离线）
//
// 设计要点：
//   1. 输入固定为 80 字节区块头。第一遍 SHA-256 的消息长度 80B：
//      1 个满块(64B) + 1 个含 0x80 填充与长度(80*8=640 bit)的尾块。
//      第二遍 SHA-256 的输入是 32B 摘要：单块即可完成（32B 数据 + 0x80 +
//      零填充 + 长度 0x100）。
//   2. 全部计算展开在寄存器中，无共享内存/全局内存往返。
//   3. Nonce 空间按线程线性切分：nonce = start + (tid * iters) + i。
//   4. 目标比较：完整 256-bit 字节级比较（展示序 = 大端整数），禁止
//      "只数前导零"的捷径实现。
//   5. 命中后用 atomicCAS 抢占唯一的返回槽位。
//
// 仅用于教学与娱乐模拟，不构成任何投资建议。

#pragma once

#include <cstdint>

namespace bitcoin_pow {

// SHA-256 轮常量 K（前 64 个质数立方根小数部分）
__device__ __constant__ uint32_t K[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu,
    0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u,
    0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u,
    0xc19bf174u, 0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
    0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau, 0x983e5152u,
    0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
    0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu,
    0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u, 0xd192e819u,
    0xd6990624u, 0xf40e3585u, 0x106aa070u, 0x19a4c116u, 0x1e376c08u,
    0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu,
    0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
    0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u};

__device__ __forceinline__ uint32_t rotr(uint32_t x, int n) {
    return (x >> n) | (x << (32 - n));
}

// 32 位字节反转。SHA-256 的字是大端解释的字节组，而比特币把摘要按
// 小端 256-bit 整数解释，两者之间需要逐字字节反转。
__host__ __device__ __forceinline__ uint32_t bswap32(uint32_t x) {
    return ((x & 0x000000FFu) << 24) | ((x & 0x0000FF00u) << 8) |
           ((x & 0x00FF0000u) >> 8) | ((x & 0xFF000000u) >> 24);
}

#define CH(x, y, z)  (((x) & (y)) ^ (~(x) & (z)))
#define MAJ(x, y, z) (((x) & (y)) ^ ((x) & (z)) ^ ((y) & (z)))
#define EP0(x)       (rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22))
#define EP1(x)       (rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25))
#define SIG0(x)      (rotr(x, 7) ^ rotr(x, 18) ^ ((x) >> 3))
#define SIG1(x)      (rotr(x, 17) ^ rotr(x, 19) ^ ((x) >> 10))

// 对 16 个大端字（64 字节消息块）做一次完整 SHA-256 压缩。
// state 输入/输出均为 8 个大端字。
__device__ __forceinline__ void sha256_compress(uint32_t state[8],
                                                const uint32_t block[16]) {
    uint32_t w[64];
#pragma unroll
    for (int i = 0; i < 16; ++i) w[i] = block[i];
#pragma unroll
    for (int i = 16; i < 64; ++i)
        w[i] = SIG1(w[i - 2]) + w[i - 7] + SIG0(w[i - 15]) + w[i - 16];

    uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
    uint32_t e = state[4], f = state[5], g = state[6], h = state[7];
#pragma unroll
    for (int i = 0; i < 64; ++i) {
        uint32_t t1 = h + EP1(e) + CH(e, f, g) + K[i] + w[i];
        uint32_t t2 = EP0(a) + MAJ(a, b, c);
        h = g; g = f; f = e; e = d + t1;
        d = c; c = b; b = a; a = t1 + t2;
    }
    state[0] += a; state[1] += b; state[2] += c; state[3] += d;
    state[4] += e; state[5] += f; state[6] += g; state[7] += h;
}

// 80 字节区块头（大端字数组，20 个字）的双重 SHA-256。
// 输出 digest 为 8 个大端字（SHA-256 原始输出顺序）。
__device__ __forceinline__ void sha256d_header(const uint32_t hdr[20],
                                               uint32_t digest[8]) {
    // ---- 第一遍：消息 = 80B = 块1(64B) + 块2(16B 数据/填充) ----
    uint32_t state1[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u,
                          0xa54ff53au, 0x510e527fu, 0x9b05688cu,
                          0x1f83d9abu, 0x5be0cd19u};
    uint32_t blk[16];
#pragma unroll
    for (int i = 0; i < 16; ++i) blk[i] = hdr[i];
    sha256_compress(state1, blk);

    // 第二块：hdr[16..19] + 0x80 + 零填充 + 位长度 640
#pragma unroll
    for (int i = 0; i < 16; ++i) blk[i] = 0u;
#pragma unroll
    for (int i = 0; i < 4; ++i) blk[i] = hdr[16 + i];
    blk[4] = 0x80000000u;
    blk[15] = 640u;                       // 80 * 8 bit
    sha256_compress(state1, blk);

    // ---- 第二遍：消息 = 32B 摘要，单块 ----
    uint32_t state2[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u,
                          0xa54ff53au, 0x510e527fu, 0x9b05688cu,
                          0x1f83d9abu, 0x5be0cd19u};
#pragma unroll
    for (int i = 0; i < 16; ++i) blk[i] = 0u;
#pragma unroll
    for (int i = 0; i < 8; ++i) blk[i] = state1[i];
    blk[8] = 0x80000000u;
    blk[15] = 256u;                       // 32 * 8 bit
    sha256_compress(state2, blk);

#pragma unroll
    for (int i = 0; i < 8; ++i) digest[i] = state2[i];
}

// 完整 256-bit 比较：H <= T。
// digest 为 8 个 SHA-256 输出大端字（协议序）；target 为 8 个字，按
// 目标整数的 32 位分组（target[7] 为最高位字）。
// 比特币整数值 V = int(展示序十六进制, 16)，其 32 位字满足：
//   V 的第 k 个字（自高位）= bswap32(digest[7-k])
// 因此比较 bswap32 后的 digest 字与 target 字（完整 256-bit 比较）。
__device__ __forceinline__ bool hash_le_target(const uint32_t digest[8],
                                               const uint32_t target[8]) {
#pragma unroll
    for (int i = 0; i < 8; ++i) {
        const uint32_t h_word = bswap32(digest[7 - i]);   // i=0 为最高位字
        const uint32_t t_word = target[7 - i];
        if (h_word != t_word) return h_word < t_word;
    }
    return true;   // 完全相等也算满足
}

}  // namespace bitcoin_pow
