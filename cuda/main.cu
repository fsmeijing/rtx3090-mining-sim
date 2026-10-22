// main.cu — RTX 3090 比特币 SHA-256d Nonce 搜索（教学用途，完全离线）
//
// 与 Python 端的契约（bitcoin_pow/gpu.py）：
//   sha256d_miner --header-hex <160 hex> --target-hex <64 hex>
//                  --start-nonce N --seconds S --max-attempts N --json
//   输出：JSON（device_name/sm_count/cuda_runtime_version/driver_version/
//          start_nonce/end_nonce/attempts/elapsed_seconds/hash_rate/
//          found/nonce/hash_hex/reason）
//
// 安全边界：
//   * 每轮 kernel launch 每线程迭代数有上限（--iters，默认 64）。
//   * 总时长与总尝试次数由 CPU 侧循环强制执行。
//   * 本程序只报告原始结果；最终"成功"必须由 Python 端 CPU 复核确认。

#include <cuda_runtime.h>

#include <cctype>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "sha256d.cuh"

namespace {

constexpr int kDefaultThreadsPerBlock = 256;
constexpr int kDefaultBlocksMultiplier = 16;   // 每 SM 的 block 数
constexpr int kDefaultItersPerThread = 64;
constexpr unsigned long long kMaxAttemptsHardCap = 1ULL << 40;

struct Options {
    std::string header_hex;
    std::string target_hex;
    unsigned long long start_nonce = 0;
    double seconds = 30.0;
    unsigned long long max_attempts = kMaxAttemptsHardCap;
    bool json = false;
    int iters = kDefaultItersPerThread;
    int threads_per_block = kDefaultThreadsPerBlock;
};

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
        // 展示序第 i 组对应 bits (224-32i .. 256-32i) -> 字索引 7-i
        words[7 - i] = w;
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

struct DeviceResult {
    int found = 0;                       // 原子标志：0 未命中，1 已命中
    int padding = 0;
    unsigned long long nonce = 0;
    uint32_t digest[8] = {0};            // SHA-256 输出大端字
};

__global__ void sha256d_mine_kernel(const uint32_t* header,  // 20 字（含 nonce=0 位）
                                    const uint32_t* target,  // 8 字
                                    unsigned long long start_nonce,
                                    int iters,
                                    DeviceResult* result) {
    const uint32_t tid = blockIdx.x * blockDim.x + threadIdx.x;
    const unsigned long long base =
        start_nonce + (unsigned long long)tid * (unsigned long long)iters;

    uint32_t local[20];
#pragma unroll
    for (int i = 0; i < 20; ++i) local[i] = header[i];

    for (int j = 0; j < iters; ++j) {
        if (result->found) return;                      // 早期退出
        const unsigned long long nonce = base + (unsigned long long)j;
        if (nonce >= 0x100000000ULL) return;            // Nonce 只有 32 位
        // 协议把 Nonce 以小端写入区块头（字节 76..79），而 SHA 字是
        // 大端解释，因此写入 bswap32(Nonce数值)。
        local[19] = bitcoin_pow::bswap32((uint32_t)nonce);

        uint32_t digest[8];
        bitcoin_pow::sha256d_header(local, digest);

        if (bitcoin_pow::hash_le_target(digest, target)) {
            if (atomicCAS(&result->found, 0, 1) == 0) { // 只保留第一个命中
                result->nonce = nonce;
#pragma unroll
                for (int i = 0; i < 8; ++i) result->digest[i] = digest[i];
            }
            return;
        }
    }
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

}  // namespace

int main(int argc, char** argv) {
    Options opt;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto next = [&](std::string* dst) -> bool {
            if (i + 1 >= argc) return false;
            *dst = argv[++i];
            return true;
        };
        if (a == "--header-hex") { if (!next(&opt.header_hex)) return 2; }
        else if (a == "--target-hex") { if (!next(&opt.target_hex)) return 2; }
        else if (a == "--start-nonce") { opt.start_nonce = strtoull(argv[++i], nullptr, 10); }
        else if (a == "--seconds") { opt.seconds = atof(argv[++i]); }
        else if (a == "--max-attempts") { opt.max_attempts = strtoull(argv[++i], nullptr, 10); }
        else if (a == "--iters") { opt.iters = atoi(argv[++i]); }
        else if (a == "--threads-per-block") { opt.threads_per_block = atoi(argv[++i]); }
        else if (a == "--json") { opt.json = true; }
        else { fprintf(stderr, "未知参数: %s\n", a.c_str()); return 2; }
    }

    uint32_t header[20], target[8];
    if (!parse_header_words(opt.header_hex, header) ||
        !parse_target_words(opt.target_hex, target)) {
        fprintf(stderr, "header/target 解析失败\n");
        return 2;
    }
    if (opt.iters < 1 || opt.iters > 4096) {
        fprintf(stderr, "每线程迭代数必须在 1..4096（安全边界）\n");
        return 2;
    }

    // ---- 设备信息 ----
    cudaDeviceProp prop{};
    int device = 0;
    cudaError_t err = cudaGetDevice(&device);
    if (err != cudaSuccess) {
        fprintf(stderr, "无可用 CUDA 设备: %s\n", cudaGetErrorString(err));
        return 3;
    }
    cudaGetDeviceProperties(&prop, device);
    int runtime_version = 0, driver_version = 0;
    cudaRuntimeGetVersion(&runtime_version);
    cudaDriverGetVersion(&driver_version);

    const int sm_count = prop.multiProcessorCount;
    const int blocks_per_launch = sm_count * kDefaultBlocksMultiplier;

    // ---- 设备内存 ----
    uint32_t *d_header = nullptr, *d_target = nullptr;
    DeviceResult* d_result = nullptr;
    cudaMalloc(&d_header, sizeof(header));
    cudaMalloc(&d_target, sizeof(target));
    cudaMalloc(&d_result, sizeof(DeviceResult));
    cudaMemcpy(d_header, header, sizeof(header), cudaMemcpyHostToDevice);
    cudaMemcpy(d_target, target, sizeof(target), cudaMemcpyHostToDevice);

    DeviceResult host_result{};
    host_result.found = 0;
    cudaMemcpy(d_result, &host_result, sizeof(DeviceResult), cudaMemcpyHostToDevice);

    // ---- CPU 侧调度循环：强制 seconds / max-attempts 上限 ----
    auto t0 = std::chrono::steady_clock::now();
    unsigned long long attempts = 0;
    unsigned long long attempts_cap =
        opt.max_attempts < kMaxAttemptsHardCap ? opt.max_attempts : kMaxAttemptsHardCap;
    double elapsed = 0.0;
    int rounds = 0;
    unsigned long long search_begin = opt.start_nonce;
    unsigned long long search_end = search_begin;   // 运行中动态推进

    const unsigned long long per_launch =
        (unsigned long long)blocks_per_launch * opt.threads_per_block * opt.iters;

    // 注意：max-attempts 上限按"整轮 launch"粒度生效，
    // 实际累计尝试最多超出上限一个 per_launch（≤ 每轮尝试数），如实报告。
    while (true) {
        // 时间上限检查
        elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
        if (elapsed >= opt.seconds) break;

        sha256d_mine_kernel<<<blocks_per_launch, opt.threads_per_block>>>(
            d_header, d_target, search_begin, opt.iters, d_result);
        cudaDeviceSynchronize();

        attempts += per_launch;
        search_end = search_begin + per_launch;
        search_begin = search_end;
        ++rounds;

        cudaMemcpy(&host_result, d_result, sizeof(DeviceResult), cudaMemcpyDeviceToHost);
        if (host_result.found) break;
        if (attempts >= attempts_cap) break;
        // Nonce 空间耗尽检查
        if (search_begin >= 0x100000000ULL) break;
    }

    elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();

    // ---- 结果回传 ----
    cudaMemcpy(&host_result, d_result, sizeof(DeviceResult), cudaMemcpyDeviceToHost);

    char digest_hex[65];
    for (int i = 0; i < 8; ++i)   // 展示序第 i 字 = bswap32(digest[7-i])
        snprintf(digest_hex + i * 8, 9, "%08x",
                 bitcoin_pow::bswap32(host_result.digest[7 - i]));
    digest_hex[64] = '\0';

    const bool found = host_result.found != 0;
    const char* reason = found ? "found"
                         : (attempts >= attempts_cap ? "max-attempts" : "exhausted");
    const double hash_rate = elapsed > 0 ? (double)attempts / elapsed : 0.0;

    cudaFree(d_header);
    cudaFree(d_target);
    cudaFree(d_result);

    if (opt.json) {
        printf("{\n");
        printf("  \"device_name\": \"%s\",\n", json_escape(prop.name).c_str());
        printf("  \"sm_count\": %d,\n", sm_count);
        printf("  \"cuda_runtime_version\": \"%d.%d\",\n",
               runtime_version / 1000, (runtime_version % 1000) / 10);
        printf("  \"driver_version\": \"%d.%d\",\n",
               driver_version / 1000, (driver_version % 1000) / 10);
        printf("  \"start_nonce\": %llu,\n", (unsigned long long)opt.start_nonce);
        printf("  \"end_nonce\": %llu,\n", search_end);
        printf("  \"attempts\": %llu,\n", attempts);
        printf("  \"rounds\": %d,\n", rounds);
        printf("  \"per_launch\": %llu,\n", per_launch);
        printf("  \"elapsed_seconds\": %.6f,\n", elapsed);
        printf("  \"hash_rate\": %.1f,\n", hash_rate);
        printf("  \"found\": %s,\n", found ? "true" : "false");
        printf("  \"nonce\": %llu,\n", host_result.nonce);
        printf("  \"hash_hex\": \"%s\",\n", found ? digest_hex : "");
        printf("  \"reason\": \"%s\"\n", reason);
        printf("}\n");
    } else {
        printf("device=%s sm=%d attempts=%llu elapsed=%.3fs rate=%.1f H/s found=%s\n",
               prop.name, sm_count, attempts, elapsed, hash_rate,
               found ? "true" : "false");
        if (found) printf("nonce=%llu hash=%s\n", host_result.nonce, digest_hex);
    }
    return found ? 0 : 1;
}
