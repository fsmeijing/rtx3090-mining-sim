// main.cu — RTX 3090 比特币 SHA-256d Nonce 搜索（教学用途，完全离线）
//
// 与 Python 端的契约（bitcoin_pow/gpu.py）：
//   sha256d_miner --header-hex <160 hex> [--target-hex <64 hex>]
//                 --mode search|fixed-work --start-nonce N --seconds S
//                 --max-attempts N [--rounds R] [--json]
//   退出码：0 = 正常执行（含未命中）；2 = 参数错误；3 = CUDA 执行错误。
//   JSON 状态：status ∈ {"RUN_FOUND","RUN_NO_HIT"}（参数/CUDA 错误不产出 JSON，
//             只输出 stderr 与非零退出码）。
//
// 精确预算契约（v3）：
//   * Host 端为每轮 launch 确定精确的 Nonce 窗口 [window_start, window_end)：
//       window_end = min(start + 剩余预算, 2^32, start + GPU单轮覆盖)
//   * 窗口上界传入 Kernel；线程只计算 nonce < window_end 的哈希，
//     窗口外的线程/迭代不执行任何 SHA-256d。
//   * scheduled_attempts = Σ(window_end - window_start)   —— 有效分配的候选
//     Nonce 数量（精确，不再是"整块分配"的粗略值）。
//   * completed_hashes   = Kernel atomicAdd 累计的实际完成 SHA-256d 数。
//   * 不变式：completed <= scheduled <= max_attempts（命中提前退出时
//     completed 进一步减小，差值如实保留）。
//
// 固定工作量模式（--mode fixed-work）：
//   不做 H<=T 判定、不因命中提前退出；严格受 max-attempts（每次运行的
//   预算）、--rounds、--seconds 三重限制，优先记录最早触发的结束条件。
//
// 安全边界：
//   * 每轮 launch 的每线程迭代数上限（--iters ≤ 4096）。
//   * 所有 CUDA API 调用检查返回码；内核启动后检查 cudaGetLastError。
//   * 参数非法一律 exit 2；CUDA 错误 exit 3。

#include <cuda_runtime.h>

#include <algorithm>
#include <cerrno>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "sha256d.cuh"

namespace {

constexpr int kDefaultThreadsPerBlock = 256;
constexpr int kDefaultBlocksMultiplier = 16;   // 每 SM 的 block 数（并行度上限）
constexpr int kDefaultItersPerThread = 64;
constexpr unsigned long long kMaxAttemptsHardCap = 1ULL << 40;
constexpr unsigned long long kNonceSpace = 0x100000000ULL;  // 2^32

constexpr int kExitOk = 0;
constexpr int kExitParam = 2;
constexpr int kExitCuda = 3;

struct Options {
    std::string header_hex;
    std::string target_hex;
    std::string mode = "search";            // search | fixed-work
    unsigned long long start_nonce = 0;
    unsigned long long max_attempts = kMaxAttemptsHardCap;
    double seconds = 30.0;
    bool json = false;
    int iters = kDefaultItersPerThread;
    int threads_per_block = kDefaultThreadsPerBlock;
    int blocks_multiplier = kDefaultBlocksMultiplier;
    unsigned long long rounds = 0;          // fixed-work 模式：0 = 不限轮数
};

#define CUDA_CHECK(call)                                                     \
    do {                                                                     \
        cudaError_t err_ = (call);                                           \
        if (err_ != cudaSuccess) {                                           \
            fprintf(stderr, "CUDA_ERROR %s:%d %s: %s\n", __FILE__, __LINE__, \
                    #call, cudaGetErrorString(err_));                        \
            return kExitCuda;                                                \
        }                                                                    \
    } while (0)

bool parse_hex_nibble(char c, uint8_t* out) {
    if (c >= '0' && c <= '9') { *out = static_cast<uint8_t>(c - '0'); return true; }
    if (c >= 'a' && c <= 'f') { *out = static_cast<uint8_t>(c - 'a' + 10); return true; }
    if (c >= 'A' && c <= 'F') { *out = static_cast<uint8_t>(c - 'A' + 10); return true; }
    return false;
}

bool parse_hex_bytes(const std::string& hex, std::vector<uint8_t>* out) {
    if (hex.size() % 2 != 0) return false;
    out->clear();
    out->reserve(hex.size() / 2);
    for (size_t i = 0; i < hex.size(); i += 2) {
        uint8_t hi, lo;
        if (!parse_hex_nibble(hex[i], &hi) || !parse_hex_nibble(hex[i + 1], &lo))
            return false;
        out->push_back(static_cast<uint8_t>((hi << 4) | lo));
    }
    return true;
}

// 目标：64 hex（大端展示序，即整数常规写法）-> 8 个字，target[7] 为最高位字
bool parse_target_words(const std::string& hex, uint32_t words[8]) {
    std::vector<uint8_t> bytes;
    if (!parse_hex_bytes(hex, &bytes) || bytes.size() != 32) return false;
    for (int i = 0; i < 8; ++i) {
        const uint8_t* p = &bytes[i * 4];   // 展示序第 i 个 4 字节组
        uint32_t w = (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) |
                     (uint32_t(p[2]) << 8) | uint32_t(p[3]);
        words[7 - i] = w;                   // 展示序第 i 组 -> 字索引 7-i
    }
    return true;
}

// 区块头：160 hex（协议序）-> 20 个大端字
bool parse_header_words(const std::string& hex, uint32_t words[20]) {
    std::vector<uint8_t> bytes;
    if (!parse_hex_bytes(hex, &bytes) || bytes.size() != 80) return false;
    for (int i = 0; i < 20; ++i) {
        const uint8_t* p = &bytes[i * 4];
        words[i] = (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) |
                   (uint32_t(p[2]) << 8) | uint32_t(p[3]);
    }
    return true;
}

// 严格无符号整数解析（拒绝负数/垃圾/溢出）；负号会被 strtoull 接受，需排除。
bool parse_ull(const char* s, unsigned long long* out) {
    if (s == nullptr || *s == '\0') return false;
    for (const char* p = s; *p; ++p)
        if (!isdigit(static_cast<unsigned char>(*p))) return false;
    errno = 0;
    char* end = nullptr;
    unsigned long long v = strtoull(s, &end, 10);
    if (errno != 0 || end == s || *end != '\0') return false;
    *out = v;
    return true;
}

// 严格正浮点解析（必须 > 0 且有限）。
bool parse_positive_seconds(const char* s, double* out) {
    if (s == nullptr || *s == '\0') return false;
    char* end = nullptr;
    double v = strtod(s, &end);
    if (end == s || *end != '\0') return false;
    if (!std::isfinite(v) || v <= 0.0) return false;
    *out = v;
    return true;
}

struct DeviceResult {
    int found = 0;                       // 原子标志：0 未命中，1 已命中
    int padding = 0;
    unsigned long long nonce = 0;
    uint32_t digest[8] = {0};            // SHA-256 输出大端字
};

// 搜索内核：窗口 [window_start, window_end) 内逐 Nonce 计算；
// nonce >= window_end 的迭代直接 break，不执行任何 SHA-256d。
// completed 只累计真实完成的哈希数（atomicAdd）。
__global__ void sha256d_mine_kernel(const uint32_t* header,   // 20 字
                                    const uint32_t* target,   // 8 字
                                    unsigned long long window_start,
                                    unsigned long long window_end,
                                    int iters,
                                    DeviceResult* result,
                                    unsigned long long* completed) {
    const uint32_t tid = blockIdx.x * blockDim.x + threadIdx.x;
    const unsigned long long base = window_start + (unsigned long long)tid * iters;
    if (base >= window_end) return;                        // 窗口外线程：不计算

    uint32_t local[20];
#pragma unroll
    for (int i = 0; i < 20; ++i) local[i] = header[i];

    unsigned long long done = 0;
    for (int j = 0; j < iters; ++j) {
        const unsigned long long nonce = base + (unsigned long long)j;
        if (nonce >= window_end) break;                    // 精确预算上界
        if (result->found) break;                          // 命中后提前退出
        local[19] = bitcoin_pow::bswap32((uint32_t)nonce); // 协议小端 Nonce
        uint32_t digest[8];
        bitcoin_pow::sha256d_header(local, digest);
        ++done;
        if (bitcoin_pow::hash_le_target(digest, target)) {
            if (atomicCAS(&result->found, 0, 1) == 0) {
                result->nonce = nonce;
#pragma unroll
                for (int i = 0; i < 8; ++i) result->digest[i] = digest[i];
            }
            break;
        }
    }
    if (done > 0) atomicAdd(completed, done);              // 只统计真实完成量
}

// 固定工作量内核：无目标判定、无命中提前退出，但同样受窗口上界约束。
// sink 防止编译器把"结果未被使用"的哈希计算优化掉。
__global__ void sha256d_fixed_kernel(const uint32_t* header,  // 20 字
                                     unsigned long long window_start,
                                     unsigned long long window_end,
                                     int iters,
                                     DeviceResult* result,    // 仅作防优化 sink
                                     unsigned long long* completed) {
    const uint32_t tid = blockIdx.x * blockDim.x + threadIdx.x;
    const unsigned long long base = window_start + (unsigned long long)tid * iters;
    if (base >= window_end) return;

    uint32_t local[20];
#pragma unroll
    for (int i = 0; i < 20; ++i) local[i] = header[i];

    unsigned long long done = 0;
    uint32_t sink = 0;
    for (int j = 0; j < iters; ++j) {
        const unsigned long long nonce = base + (unsigned long long)j;
        if (nonce >= window_end) break;                    // 精确预算上界
        local[19] = bitcoin_pow::bswap32((uint32_t)nonce);
        uint32_t digest[8];
        bitcoin_pow::sha256d_header(local, digest);
        sink ^= digest[0];
        ++done;
    }
    if (sink == 0xDEADBEEFu) result->found = 1;            // 永不成立，防优化
    if (done > 0) atomicAdd(completed, done);
}

std::string json_escape(const std::string& s) {
    std::string out;
    for (char c : s) {
        if (c == '"' || c == '\\') { out += '\\'; out += c; }
        else if (static_cast<unsigned char>(c) < 0x20) out += ' ';
        else out += c;
    }
    return out;
}

void print_json(const cudaDeviceProp& prop, int sm_count,
                int runtime_version, int driver_version, const Options& opt,
                const std::string& status, const std::string& reason,
                unsigned long long scheduled, unsigned long long completed,
                double elapsed, int rounds, unsigned long long nonce_begin,
                unsigned long long nonce_end, bool found,
                unsigned long long hit_nonce, const char* digest_hex) {
    const double hash_rate =
        elapsed > 0 ? (double)completed / elapsed : 0.0;
    printf("{\n");
    printf("  \"status\": \"%s\",\n", status.c_str());
    printf("  \"mode\": \"%s\",\n", opt.mode.c_str());
    printf("  \"device_name\": \"%s\",\n", json_escape(prop.name).c_str());
    printf("  \"sm_count\": %d,\n", sm_count);
    printf("  \"cuda_runtime_version\": \"%d.%d\",\n",
           runtime_version / 1000, (runtime_version % 1000) / 10);
    printf("  \"driver_version\": \"%d.%d\",\n",
           driver_version / 1000, (driver_version % 1000) / 10);
    printf("  \"max_attempts_budget\": %llu,\n", opt.max_attempts);
    printf("  \"start_nonce\": %llu,\n", nonce_begin);
    printf("  \"end_nonce\": %llu,\n", nonce_end);
    printf("  \"scheduled_attempts\": %llu,\n", scheduled);
    printf("  \"completed_hashes\": %llu,\n", completed);
    printf("  \"rounds\": %d,\n", rounds);
    printf("  \"elapsed_seconds\": %.6f,\n", elapsed);
    printf("  \"hash_rate\": %.1f,\n", hash_rate);
    printf("  \"found\": %s,\n", found ? "true" : "false");
    printf("  \"nonce\": %llu,\n", hit_nonce);
    printf("  \"hash_hex\": \"%s\",\n", found ? digest_hex : "");
    printf("  \"reason\": \"%s\"\n", reason.c_str());
    printf("}\n");
}

}  // namespace

int main(int argc, char** argv) {
    Options opt;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto next = [&](std::string* dst) -> bool {
            if (i + 1 >= argc) return false;   // 缺参数值
            *dst = argv[++i];
            return true;
        };
        if (a == "--header-hex") { if (!next(&opt.header_hex)) return kExitParam; }
        else if (a == "--target-hex") { if (!next(&opt.target_hex)) return kExitParam; }
        else if (a == "--mode") { if (!next(&opt.mode)) return kExitParam; }
        else if (a == "--start-nonce") {
            std::string v;
            if (!next(&v) || !parse_ull(v.c_str(), &opt.start_nonce)) {
                fprintf(stderr, "PARAM_ERROR --start-nonce 非法: %s\n", v.c_str());
                return kExitParam;
            }
        }
        else if (a == "--seconds") {
            std::string v;
            if (!next(&v) || !parse_positive_seconds(v.c_str(), &opt.seconds)) {
                fprintf(stderr, "PARAM_ERROR --seconds 必须为正且有限: %s\n", v.c_str());
                return kExitParam;
            }
        }
        else if (a == "--max-attempts") {
            std::string v;
            if (!next(&v) || !parse_ull(v.c_str(), &opt.max_attempts) ||
                opt.max_attempts < 1) {
                fprintf(stderr, "PARAM_ERROR --max-attempts 必须 >= 1: %s\n", v.c_str());
                return kExitParam;
            }
            opt.max_attempts = opt.max_attempts < kMaxAttemptsHardCap
                                   ? opt.max_attempts : kMaxAttemptsHardCap;
        }
        else if (a == "--rounds") {
            std::string v;
            if (!next(&v) || !parse_ull(v.c_str(), &opt.rounds) || opt.rounds < 1) {
                fprintf(stderr, "PARAM_ERROR --rounds 必须 >= 1: %s\n", v.c_str());
                return kExitParam;
            }
        }
        else if (a == "--iters") {
            std::string v;
            unsigned long long n;
            if (!next(&v) || !parse_ull(v.c_str(), &n) || n < 1 || n > 4096) {
                fprintf(stderr, "PARAM_ERROR --iters 必须在 1..4096: %s\n", v.c_str());
                return kExitParam;
            }
            opt.iters = (int)n;
        }
        else if (a == "--threads-per-block") {
            std::string v;
            unsigned long long n;
            if (!next(&v) || !parse_ull(v.c_str(), &n) || n < 32 || n > 1024 ||
                (n & (n - 1)) != 0) {
                fprintf(stderr, "PARAM_ERROR --threads-per-block 必须为 32..1024 的 2 的幂: %s\n",
                        v.c_str());
                return kExitParam;
            }
            opt.threads_per_block = (int)n;
        }
        else if (a == "--json") { opt.json = true; }
        else { fprintf(stderr, "PARAM_ERROR 未知参数: %s\n", a.c_str()); return kExitParam; }
    }

    if (opt.header_hex.empty()) {
        fprintf(stderr, "PARAM_ERROR 缺少 --header-hex\n");
        return kExitParam;
    }
    if (opt.mode != "search" && opt.mode != "fixed-work") {
        fprintf(stderr, "PARAM_ERROR --mode 必须为 search 或 fixed-work: %s\n",
                opt.mode.c_str());
        return kExitParam;
    }
    if (opt.mode == "search" && opt.target_hex.empty()) {
        fprintf(stderr, "PARAM_ERROR search 模式缺少 --target-hex\n");
        return kExitParam;
    }
    if (opt.start_nonce >= kNonceSpace) {
        fprintf(stderr, "PARAM_ERROR --start-nonce 超出 32-bit Nonce 空间: %llu\n",
                opt.start_nonce);
        return kExitParam;
    }

    uint32_t header[20], target[8] = {0};
    if (!parse_header_words(opt.header_hex, header)) {
        fprintf(stderr, "PARAM_ERROR header 解析失败（需 160 个十六进制字符）\n");
        return kExitParam;
    }
    if (opt.mode == "search" && !parse_target_words(opt.target_hex, target)) {
        fprintf(stderr, "PARAM_ERROR target 解析失败（需 64 个十六进制字符）\n");
        return kExitParam;
    }

    // ---- 设备信息（全部检查返回码） ----
    cudaDeviceProp prop{};
    int device = 0;
    CUDA_CHECK(cudaGetDevice(&device));
    CUDA_CHECK(cudaGetDeviceProperties(&prop, device));
    int runtime_version = 0, driver_version = 0;
    CUDA_CHECK(cudaRuntimeGetVersion(&runtime_version));
    CUDA_CHECK(cudaDriverGetVersion(&driver_version));
    const int sm_count = prop.multiProcessorCount;

    // ---- 设备内存 ----
    uint32_t *d_header = nullptr, *d_target = nullptr;
    DeviceResult* d_result = nullptr;
    unsigned long long* d_completed = nullptr;
    CUDA_CHECK(cudaMalloc(&d_header, sizeof(header)));
    CUDA_CHECK(cudaMalloc(&d_target, sizeof(target)));
    CUDA_CHECK(cudaMalloc(&d_result, sizeof(DeviceResult)));
    CUDA_CHECK(cudaMalloc(&d_completed, sizeof(unsigned long long)));
    CUDA_CHECK(cudaMemcpy(d_header, header, sizeof(header), cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(d_target, target, sizeof(target), cudaMemcpyHostToDevice));

    DeviceResult host_result{};
    unsigned long long host_completed = 0;

    auto t0 = std::chrono::steady_clock::now();
    auto elapsed_now = [&]() {
        return std::chrono::duration<double>(
                   std::chrono::steady_clock::now() - t0).count();
    };

    // GPU 单轮最大覆盖（并行度上限）：sm×multiplier 个 block
    const unsigned long long gpu_cover_max =
        (unsigned long long)sm_count * opt.blocks_multiplier *
        (unsigned long long)opt.threads_per_block * (unsigned long long)opt.iters;

    unsigned long long scheduled = 0, completed = 0;
    unsigned long long nonce_begin = opt.start_nonce, nonce_end = opt.start_nonce;
    int rounds_done = 0;
    double elapsed = 0.0;
    bool found = false;
    std::string reason;

    // 计算一轮窗口：窗口上界 = min(剩余预算, 2^32, GPU单轮覆盖)
    auto next_window = [&](unsigned long long budget_left)
        -> std::pair<unsigned long long, int> {
        const unsigned long long range_end =
            std::min(nonce_begin + budget_left, kNonceSpace);
        const unsigned long long window_end =
            std::min(range_end, nonce_begin + gpu_cover_max);
        const unsigned long long span = window_end - nonce_begin;
        const unsigned long long per_thread_work =
            (unsigned long long)opt.threads_per_block * (unsigned long long)opt.iters;
        const int blocks = (int)((span + per_thread_work - 1) / per_thread_work);
        return {window_end, blocks};
    };

    // ---- 固定工作量模式：无命中判定，受 rounds/seconds/max-attempts 三限 ----
    // reason 优先记录最早触发的结束条件（同刻触发时按 time > rounds > budget
    // 的顺序判定，该顺序已在文档中说明）。
    if (opt.mode == "fixed-work") {
        while (true) {
            elapsed = elapsed_now();
            if (elapsed >= opt.seconds) { reason = "time-limit"; break; }
            if (opt.rounds > 0 && (unsigned long long)rounds_done >= opt.rounds) {
                reason = "rounds-done";
                break;
            }
            const unsigned long long budget_left = opt.max_attempts - scheduled;
            if (budget_left == 0) { reason = "max-attempts"; break; }
            if (nonce_begin >= kNonceSpace) { reason = "nonce-space-exhausted"; break; }

            const auto [window_end, blocks] = next_window(budget_left);
            if (blocks <= 0) { reason = "nonce-space-exhausted"; break; }

            host_completed = 0;
            CUDA_CHECK(cudaMemcpy(d_completed, &host_completed,
                                  sizeof(unsigned long long), cudaMemcpyHostToDevice));
            sha256d_fixed_kernel<<<blocks, opt.threads_per_block>>>(
                d_header, nonce_begin, window_end, opt.iters, d_result, d_completed);
            cudaError_t kerr = cudaGetLastError();
            if (kerr != cudaSuccess) {
                fprintf(stderr, "CUDA_ERROR kernel launch: %s\n",
                        cudaGetErrorString(kerr));
                return kExitCuda;
            }
            CUDA_CHECK(cudaDeviceSynchronize());
            CUDA_CHECK(cudaMemcpy(&host_completed, d_completed,
                                  sizeof(unsigned long long), cudaMemcpyDeviceToHost));

            scheduled += window_end - nonce_begin;   // 精确有效分配
            completed += host_completed;             // 实际完成量
            nonce_end = window_end;
            nonce_begin = window_end;
            ++rounds_done;
        }
        elapsed = elapsed_now();
        reason = reason.empty() ? "done" : reason;
        print_json(prop, sm_count, runtime_version, driver_version, opt,
                   "RUN_NO_HIT", reason, scheduled, completed, elapsed,
                   rounds_done, opt.start_nonce, nonce_end, false, 0, "");
        cudaFree(d_header); cudaFree(d_target);
        cudaFree(d_result); cudaFree(d_completed);
        return kExitOk;
    }

    // ---- 搜索模式：窗口 + 命中提前退出，预算精确 ----
    while (true) {
        elapsed = elapsed_now();
        if (elapsed >= opt.seconds) { reason = "time-limit"; break; }
        const unsigned long long budget_left = opt.max_attempts - scheduled;
        if (budget_left == 0) { reason = "max-attempts"; break; }
        if (nonce_begin >= kNonceSpace) { reason = "nonce-space-exhausted"; break; }

        const auto [window_end, blocks] = next_window(budget_left);
        if (blocks <= 0) { reason = "nonce-space-exhausted"; break; }

        host_result.found = 0;
        host_completed = 0;
        CUDA_CHECK(cudaMemcpy(d_result, &host_result, sizeof(DeviceResult),
                              cudaMemcpyHostToDevice));
        CUDA_CHECK(cudaMemcpy(d_completed, &host_completed,
                              sizeof(unsigned long long), cudaMemcpyHostToDevice));
        sha256d_mine_kernel<<<blocks, opt.threads_per_block>>>(
            d_header, d_target, nonce_begin, window_end, opt.iters,
            d_result, d_completed);
        cudaError_t kerr = cudaGetLastError();
        if (kerr != cudaSuccess) {
            fprintf(stderr, "CUDA_ERROR kernel launch: %s\n",
                    cudaGetErrorString(kerr));
            return kExitCuda;
        }
        CUDA_CHECK(cudaDeviceSynchronize());
        CUDA_CHECK(cudaMemcpy(&host_result, d_result, sizeof(DeviceResult),
                              cudaMemcpyDeviceToHost));
        CUDA_CHECK(cudaMemcpy(&host_completed, d_completed,
                              sizeof(unsigned long long), cudaMemcpyDeviceToHost));

        scheduled += window_end - nonce_begin;
        completed += host_completed;
        nonce_end = window_end;
        nonce_begin = window_end;
        ++rounds_done;
        if (host_result.found) { found = true; reason = "found"; break; }
    }
    elapsed = elapsed_now();
    if (reason.empty()) reason = "done";
    const std::string status = found ? "RUN_FOUND" : "RUN_NO_HIT";

    char digest_hex[65] = {0};
    if (found) {
        for (int i = 0; i < 8; ++i)   // 展示序第 i 字 = bswap32(digest[7-i])
            snprintf(digest_hex + i * 8, 9, "%08x",
                     bitcoin_pow::bswap32(host_result.digest[7 - i]));
        digest_hex[64] = '\0';
    }

    if (opt.json) {
        print_json(prop, sm_count, runtime_version, driver_version, opt, status,
                   reason, scheduled, completed, elapsed, rounds_done,
                   opt.start_nonce, nonce_end, found, host_result.nonce,
                   digest_hex);
    } else {
        printf("device=%s sm=%d status=%s scheduled=%llu completed=%llu "
               "elapsed=%.3fs rate=%.1f H/s found=%s\n",
               prop.name, sm_count, status.c_str(), scheduled, completed,
               elapsed, elapsed > 0 ? (double)completed / elapsed : 0.0,
               found ? "true" : "false");
        if (found) printf("nonce=%llu hash=%s\n", host_result.nonce, digest_hex);
    }
    cudaFree(d_header); cudaFree(d_target);
    cudaFree(d_result); cudaFree(d_completed);
    return kExitOk;
}
