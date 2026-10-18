// Copyright (c) 2026
//
// Persistent RKLLM launcher for EdgeHome-AgentBench.
//
// Design goals:
//   * Qwen3 chat template with thinking disabled.
//   * No rkllm_set_function_tools() schema injection.
//   * Explicit case boundaries: START clears the previous case, TOOL continues it.
//   * Deterministic decoding for benchmark runs.
//   * Base64 line protocol so JSON/newlines/tabs cannot corrupt stdin/stdout framing.
//   * Machine-readable result markers plus performance and KV-cache diagnostics.
//
// Usage:
//   edgehome_rkllm_persistent MODEL MAX_NEW_TOKENS MAX_CONTEXT_LEN SYSTEM_PROMPT_FILE
//
// Stdin protocol (one command per line):
//   START<TAB>request_id<TAB>base64(user_content)
//   TOOL<TAB>request_id<TAB>base64(tool_result_content)
//   RESET<TAB>request_id
//   QUIT
//
// Stdout protocol:
//   __EDGEHOME_READY__
//   __EDGEHOME_RESET__<TAB>request_id
//   __EDGEHOME_RESULT__<TAB>request_id<TAB>ok|run_error<TAB>wall_ms<TAB>base64(output)
//
// Runtime diagnostics are written to stderr and never mixed into model output.

#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <unistd.h>
#include <vector>

#include "rkllm.h"

using std::cerr;
using std::cin;
using std::getline;
using std::ifstream;
using std::ios;
using std::string;
using std::vector;

namespace {

LLMHandle g_handle = nullptr;
string g_output;
RKLLMPerfStat g_last_perf = {};
bool g_has_perf = false;
bool g_run_error = false;
bool g_suppress_output = false;

const char kBase64Alphabet[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

bool read_text_file(const char* path, string* content) {
    if (path == nullptr || content == nullptr) return false;
    ifstream file(path, ios::in | ios::binary);
    if (!file.is_open()) return false;
    content->assign(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
    if (content->size() >= 3 &&
        static_cast<unsigned char>((*content)[0]) == 0xEF &&
        static_cast<unsigned char>((*content)[1]) == 0xBB &&
        static_cast<unsigned char>((*content)[2]) == 0xBF) {
        content->erase(0, 3);
    }
    while (!content->empty() && (content->back() == '\r' || content->back() == '\n')) {
        content->pop_back();
    }
    return !content->empty();
}

string base64_encode(const string& input) {
    string output;
    output.reserve(((input.size() + 2) / 3) * 4);
    unsigned int accumulator = 0;
    int bits = -6;
    for (unsigned char ch : input) {
        accumulator = (accumulator << 8) | ch;
        bits += 8;
        while (bits >= 0) {
            output.push_back(kBase64Alphabet[(accumulator >> bits) & 0x3F]);
            bits -= 6;
        }
    }
    if (bits > -6) {
        output.push_back(kBase64Alphabet[((accumulator << 8) >> (bits + 8)) & 0x3F]);
    }
    while (output.size() % 4 != 0) output.push_back('=');
    return output;
}

int base64_value(unsigned char ch) {
    if (ch >= 'A' && ch <= 'Z') return ch - 'A';
    if (ch >= 'a' && ch <= 'z') return ch - 'a' + 26;
    if (ch >= '0' && ch <= '9') return ch - '0' + 52;
    if (ch == '+') return 62;
    if (ch == '/') return 63;
    return -1;
}

bool base64_decode(const string& input, string* output) {
    if (output == nullptr) return false;
    output->clear();
    output->reserve((input.size() / 4) * 3);
    unsigned int accumulator = 0;
    int bits = -8;
    for (unsigned char ch : input) {
        if (ch == '=') break;
        const int value = base64_value(ch);
        if (value < 0) return false;
        accumulator = (accumulator << 6) | static_cast<unsigned int>(value);
        bits += 6;
        if (bits >= 0) {
            output->push_back(static_cast<char>((accumulator >> bits) & 0xFF));
            bits -= 8;
        }
    }
    return true;
}

vector<string> split_tabs(const string& line) {
    vector<string> parts;
    size_t begin = 0;
    while (true) {
        const size_t end = line.find('\t', begin);
        if (end == string::npos) {
            parts.push_back(line.substr(begin));
            break;
        }
        parts.push_back(line.substr(begin, end - begin));
        begin = end + 1;
    }
    return parts;
}

void destroy_model() {
    if (g_handle != nullptr) {
        LLMHandle handle = g_handle;
        g_handle = nullptr;
        rkllm_destroy(handle);
    }
}

void signal_handler(int signal_number) {
    (void)signal_number;
    destroy_model();
    std::_Exit(0);
}

int result_callback(RKLLMResult* result, void* userdata, LLMCallState state) {
    (void)userdata;
    if (state == RKLLM_RUN_NORMAL && result != nullptr && result->text != nullptr) {
        if (!g_suppress_output) g_output.append(result->text);
    } else if (state == RKLLM_RUN_FINISH) {
        if (result != nullptr) {
            g_last_perf = result->perf;
            g_has_perf = true;
        }
    } else if (state == RKLLM_RUN_ERROR) {
        g_run_error = true;
    }
    return 0;
}

int current_kv_positions() {
    int sizes[1] = {0};
    const int ret = rkllm_get_kv_cache_size(g_handle, sizes);
    return ret == 0 ? sizes[0] : -1;
}

bool clear_case_history(const string& request_id) {
    // Keep the static system prompt installed by rkllm_set_chat_template(),
    // but remove all user/tool/assistant tokens belonging to the prior case.
    const int ret = rkllm_clear_kv_cache(g_handle, 1, nullptr, nullptr);
    if (ret != 0) {
        fprintf(stderr, "[edgehome-reset] id=%s failed=%d\n", request_id.c_str(), ret);
        return false;
    }
    fprintf(stderr, "[edgehome-reset] id=%s kv_positions=%d\n",
            request_id.c_str(), current_kv_positions());
    return true;
}

void reset_run_state() {
    g_output.clear();
    g_last_perf = RKLLMPerfStat{};
    g_has_perf = false;
    g_run_error = false;
}

int run_turn(const string& request_id, const char* role, const string& content) {
    reset_run_state();
    const int kv_before = current_kv_positions();

    RKLLMInput input;
    std::memset(&input, 0, sizeof(input));
    input.input_type = RKLLM_INPUT_PROMPT;
    input.role = role;
    input.enable_thinking = false;
    input.prompt_input = const_cast<char*>(content.c_str());

    RKLLMInferParam infer;
    std::memset(&infer, 0, sizeof(infer));
    infer.mode = RKLLM_INFER_GENERATE;
    infer.keep_history = 1;

    const auto started = std::chrono::steady_clock::now();
    const int ret = rkllm_run(g_handle, &input, &infer, nullptr);
    const auto finished = std::chrono::steady_clock::now();
    const double wall_ms =
        std::chrono::duration<double, std::milli>(finished - started).count();
    const int kv_after = current_kv_positions();

    if (g_has_perf) {
        const float prefill_tps = g_last_perf.prefill_time_ms > 0.0f
            ? g_last_perf.prefill_tokens * 1000.0f / g_last_perf.prefill_time_ms : 0.0f;
        const float decode_tps = g_last_perf.generate_time_ms > 0.0f
            ? g_last_perf.generate_tokens * 1000.0f / g_last_perf.generate_time_ms : 0.0f;
        fprintf(stderr,
                "[edgehome-perf] id=%s role=%s prefill_ms=%.1f prefill_tokens=%d "
                "prefill_tps=%.2f decode_ms=%.1f decode_tokens=%d decode_tps=%.2f "
                "memory_mb=%.1f wall_ms=%.3f kv_before=%d kv_after=%d\n",
                request_id.c_str(), role,
                g_last_perf.prefill_time_ms, g_last_perf.prefill_tokens, prefill_tps,
                g_last_perf.generate_time_ms, g_last_perf.generate_tokens, decode_tps,
                g_last_perf.memory_usage_mb, wall_ms, kv_before, kv_after);
    } else {
        fprintf(stderr,
                "[edgehome-perf] id=%s role=%s perf_unavailable=1 wall_ms=%.3f "
                "kv_before=%d kv_after=%d\n",
                request_id.c_str(), role, wall_ms, kv_before, kv_after);
    }

    const bool ok = ret == 0 && !g_run_error;
    printf("__EDGEHOME_RESULT__\t%s\t%s\t%.3f\t%s\n",
           request_id.c_str(), ok ? "ok" : "run_error", wall_ms,
           base64_encode(g_output).c_str());
    fflush(stdout);
    return ok ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
    setvbuf(stdout, nullptr, _IONBF, 0);
    setvbuf(stderr, nullptr, _IONBF, 0);

    if (argc != 5) {
        cerr << "Usage: " << argv[0]
             << " model_path max_new_tokens max_context_len system_prompt_file\n";
        return 1;
    }

    const char* model_path = argv[1];
    const int max_new_tokens = std::atoi(argv[2]);
    const int max_context_len = std::atoi(argv[3]);
    string system_text;
    if (max_new_tokens <= 0 || max_context_len <= 0 ||
        !read_text_file(argv[4], &system_text)) {
        cerr << "Invalid token limits or unreadable system prompt: " << argv[4] << "\n";
        return 2;
    }

    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    RKLLMParam param = rkllm_createDefaultParam();
    param.model_path = model_path;
    // Greedy decoding: repeatable outputs are essential for benchmark comparison.
    param.top_k = 1;
    param.top_p = 1.0f;
    param.temperature = 1.0f;
    param.repeat_penalty = 1.0f;
    param.frequency_penalty = 0.0f;
    param.presence_penalty = 0.0f;
    param.max_new_tokens = max_new_tokens;
    param.max_context_len = max_context_len;
    param.skip_special_token = true;
    param.extend_param.base_domain_id = 0;
    param.extend_param.embed_flash = 1;

    fprintf(stderr,
            "[edgehome-init] model=%s max_new_tokens=%d max_context_len=%d "
            "top_k=1 thinking=disabled native_tools=disabled api_abi=%s\n",
            model_path, max_new_tokens, max_context_len,
#ifdef EDGEHOME_RKLLM_API_1_3
            "1.3"
#else
            "1.2"
#endif
    );

#ifdef EDGEHOME_RKLLM_API_1_3
    // RKLLM 1.3 changed rkllm_init's third argument from a bare result
    // callback to an extensible callback structure. Keep the legacy branch so
    // the same source can still reproduce the existing 1.2.3 experiments.
    RKLLMCallback callbacks = {};
    callbacks.result_callback = result_callback;
    int ret = rkllm_init(&g_handle, &param, &callbacks);
#else
    int ret = rkllm_init(&g_handle, &param, result_callback);
#endif
    if (ret != 0) {
        fprintf(stderr, "[edgehome-init] rkllm_init failed=%d\n", ret);
        destroy_model();
        return 3;
    }

    // This matches Qwen3 tokenizer.apply_chat_template(...,
    // add_generation_prompt=true, enable_thinking=false). Verify the exact
    // strings against the tokenizer_config.json of every future model family.
    const string system_prompt =
        "<|im_start|>system\n" + system_text + "<|im_end|>\n";
    const char* prompt_prefix = "<|im_start|>user\n";
    const char* prompt_postfix =
        "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n";
    ret = rkllm_set_chat_template(
        g_handle, system_prompt.c_str(), prompt_prefix, prompt_postfix);
    if (ret != 0) {
        fprintf(stderr, "[edgehome-init] rkllm_set_chat_template failed=%d\n", ret);
        destroy_model();
        return 4;
    }

    // Warm up model/runtime, then remove the synthetic turn while retaining the
    // system prompt cache. Warmup output is intentionally discarded.
    g_suppress_output = true;
    reset_run_state();
    RKLLMInput warmup_input;
    std::memset(&warmup_input, 0, sizeof(warmup_input));
    string warmup_text = "只输出一个空JSON对象。";
    warmup_input.input_type = RKLLM_INPUT_PROMPT;
    warmup_input.role = "user";
    warmup_input.enable_thinking = false;
    warmup_input.prompt_input = const_cast<char*>(warmup_text.c_str());
    RKLLMInferParam warmup_infer;
    std::memset(&warmup_infer, 0, sizeof(warmup_infer));
    warmup_infer.mode = RKLLM_INFER_GENERATE;
    warmup_infer.keep_history = 1;
    ret = rkllm_run(g_handle, &warmup_input, &warmup_infer, nullptr);
    g_suppress_output = false;
    if (ret != 0 || g_run_error || !clear_case_history("warmup")) {
        fprintf(stderr, "[edgehome-warmup] failed=%d callback_error=%d\n",
                ret, g_run_error ? 1 : 0);
        destroy_model();
        return 5;
    }
    if (g_has_perf) {
        fprintf(stderr,
                "[edgehome-warmup] prefill_ms=%.1f prefill_tokens=%d "
                "decode_ms=%.1f decode_tokens=%d memory_mb=%.1f\n",
                g_last_perf.prefill_time_ms, g_last_perf.prefill_tokens,
                g_last_perf.generate_time_ms, g_last_perf.generate_tokens,
                g_last_perf.memory_usage_mb);
    }

    printf("__EDGEHOME_READY__\n");

    string line;
    while (getline(cin, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;
        if (line == "QUIT") break;

        const vector<string> parts = split_tabs(line);
        const string operation = parts.empty() ? string() : parts[0];
        const string request_id = parts.size() >= 2 ? parts[1] : string("unknown");

        if (operation == "RESET") {
            const bool ok = clear_case_history(request_id);
            printf("__EDGEHOME_RESET__\t%s\t%s\n",
                   request_id.c_str(), ok ? "ok" : "error");
            continue;
        }
        if ((operation != "START" && operation != "TOOL") || parts.size() != 3) {
            printf("__EDGEHOME_PROTOCOL_ERROR__\t%s\tinvalid_command\n",
                   request_id.c_str());
            continue;
        }

        string content;
        if (!base64_decode(parts[2], &content)) {
            printf("__EDGEHOME_PROTOCOL_ERROR__\t%s\tinvalid_base64\n",
                   request_id.c_str());
            continue;
        }
        if (operation == "START" && !clear_case_history(request_id)) {
            printf("__EDGEHOME_RESULT__\t%s\trun_error\t0.000\t\n",
                   request_id.c_str());
            continue;
        }

        // This launcher intentionally uses a prompt-defined tool protocol and
        // does not call rkllm_set_function_tools(). RKLLM runtime 1.2.3 treats
        // role="tool" as its native function-tools transport and requires a
        // runtime-specific JSON-array payload. Our EIA observation is already
        // explicitly tagged as tool_result in the JSON content, so append it
        // as a normal user turn to preserve the portable prompt protocol used
        // by RKLLM, llama.cpp, and API backends.
        run_turn(request_id, "user", content);
    }

    destroy_model();
    return 0;
}
