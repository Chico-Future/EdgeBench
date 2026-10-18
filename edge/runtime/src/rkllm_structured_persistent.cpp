#include <chrono>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "rkllm.h"

using json = nlohmann::json;

namespace {

LLMHandle g_handle = nullptr;
std::string g_generated;
RKLLMPerfStat g_perf = {};
bool g_has_perf = false;

constexpr const char* kReady = "__TEXT_LLM_READY__";
constexpr const char* kResult = "__TEXT_LLM_RESULT__";
constexpr const char* kError = "__TEXT_LLM_ERROR__";
constexpr const char* kDiagnostic = "__STRUCTURED_DIAGNOSTIC__";
constexpr const char* kAudit = "__STRUCTURED_AUDIT__";
constexpr const char* kPerf = "__RKLLM_PERF__";

void destroy_model() {
    if (g_handle != nullptr) {
        LLMHandle handle = g_handle;
        g_handle = nullptr;
        rkllm_destroy(handle);
    }
}

void signal_handler(int) {
    destroy_model();
    std::_Exit(0);
}

int result_callback(RKLLMResult* result, void*, LLMCallState state) {
    if (state == RKLLM_RUN_NORMAL && result != nullptr && result->text != nullptr) {
        g_generated += result->text;
    } else if (state == RKLLM_RUN_FINISH) {
        if (result != nullptr) {
            g_perf = result->perf;
            g_has_perf = true;
        }
    }
    return 0;
}

std::string read_file(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot_open_file:" + path);
    return std::string(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}

std::string trim(const std::string& value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return "";
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

bool parse_exact_json_value(const std::string& raw, json* value) {
    try {
        *value = json::parse(trim(raw));
        return true;
    } catch (...) {
        return false;
    }
}

bool extract_json_value(const std::string& raw, json* value, std::string* error) {
    std::string text = trim(raw);
    if (text.rfind("```", 0) == 0) {
        const auto newline = text.find('\n');
        if (newline != std::string::npos) text = text.substr(newline + 1);
        const auto closing = text.rfind("```");
        if (closing != std::string::npos) text = text.substr(0, closing);
        text = trim(text);
    } else if (text.rfind("`json", 0) == 0 || text.rfind("`JSON", 0) == 0) {
        text = trim(text.substr(5));
        if (!text.empty() && text.back() == '`') text = trim(text.substr(0, text.size() - 1));
    } else if (!text.empty() && text.front() == '`') {
        text = trim(text.substr(1));
        if (!text.empty() && text.back() == '`') text = trim(text.substr(0, text.size() - 1));
    }
    try {
        json parsed = json::parse(text);
        *value = std::move(parsed);
        return true;
    } catch (...) {
    }

    for (size_t start = 0; start < text.size(); ++start) {
        if (text[start] != '{') continue;
        int depth = 0;
        bool in_string = false;
        bool escaped = false;
        for (size_t pos = start; pos < text.size(); ++pos) {
            const char ch = text[pos];
            if (in_string) {
                if (escaped) escaped = false;
                else if (ch == '\\') escaped = true;
                else if (ch == '"') in_string = false;
                continue;
            }
            if (ch == '"') in_string = true;
            else if (ch == '{') ++depth;
            else if (ch == '}') {
                --depth;
                if (depth == 0) {
                    try {
                        json parsed = json::parse(text.substr(start, pos - start + 1));
                        if (parsed.is_object()) {
                            *value = std::move(parsed);
                            return true;
                        }
                    } catch (...) {
                    }
                    break;
                }
            }
        }
    }
    *error = "no_valid_json_object";
    return false;
}

bool schema_mode_with_field(const json& schema, const std::string& field, std::string* mode) {
    std::vector<json> choices;
    if (schema.contains("oneOf") && schema.at("oneOf").is_array()) {
        for (const auto& item : schema.at("oneOf")) choices.push_back(item);
    } else {
        choices.push_back(schema);
    }
    for (const auto& item : choices) {
        if (!item.is_object() || !item.contains("properties")) continue;
        const auto& properties = item.at("properties");
        if (!properties.is_object() || !properties.contains(field) || !properties.contains("mode")) continue;
        const auto& mode_schema = properties.at("mode");
        if (mode_schema.is_object() && mode_schema.contains("const") && mode_schema.at("const").is_string()) {
            *mode = mode_schema.at("const").get<std::string>();
            return true;
        }
    }
    return false;
}

bool coerce_protocol_shape(const json& schema, const json& parsed, json* value, std::string* note) {
    if (parsed.is_object()) {
        json candidate = parsed;
        if (candidate.contains("tool_call_") && !candidate.contains("tool_call")) {
            candidate["tool_call"] = candidate.at("tool_call_");
            candidate.erase("tool_call_");
            *note = "renamed_tool_call_key";
        } else if (candidate.contains("name") && candidate.at("name").is_string()
                   && candidate.contains("arguments") && candidate.at("arguments").is_object()
                   && !candidate.contains("tool_call")) {
            candidate = json{{"tool_call", candidate}};
            *note = "wrapped_tool_call";
        } else if (candidate.contains("actions") && !candidate.contains("mode")) {
            std::string mode;
            if (schema_mode_with_field(schema, "actions", &mode)) {
                candidate["mode"] = mode;
                *note = "added_mode";
            }
        }

        // Small models sometimes copy JSON-Schema metadata beside an otherwise
        // valid decision.  Remove metadata only; never alter the chosen tool.
        if (candidate.contains("tool_call") || candidate.contains("final_output")) {
            const std::vector<std::string> metadata = {
                "type", "required", "properties", "additionalProperties", "oneOf", "anyOf", "$schema"
            };
            for (const auto& key : metadata) {
                if (candidate.erase(key) > 0) *note += "+removed_schema_metadata";
            }
        }

        // Another common formatting-only error is nesting the action identity
        // inside arguments. Lift those identity fields without changing values.
        if (candidate.contains("actions") && candidate.at("actions").is_array()) {
            for (auto& action : candidate["actions"]) {
                if (!action.is_object() || !action.contains("arguments") || !action["arguments"].is_object()) continue;
                auto& arguments = action["arguments"];
                if (!action.contains("device_id") && arguments.contains("device_id")) {
                    action["device_id"] = arguments["device_id"];
                    arguments.erase("device_id");
                    *note += "+lifted_device_id";
                }
                if (!action.contains("service") && arguments.contains("service")) {
                    action["service"] = arguments["service"];
                    arguments.erase("service");
                    *note += "+lifted_service";
                }
                if (arguments.contains("arguments") && arguments["arguments"].is_object()) {
                    json nested = arguments["arguments"];
                    arguments.erase("arguments");
                    for (auto it = arguments.begin(); it != arguments.end(); ++it) nested[it.key()] = it.value();
                    arguments = std::move(nested);
                    *note += "+flattened_arguments";
                }
            }
        }
        *value = std::move(candidate);
        return true;
    }
    if (parsed.is_array()) {
        std::string mode;
        if (schema_mode_with_field(schema, "actions", &mode)) {
            *value = json{{"mode", mode}, {"actions", parsed}};
            *note = "wrapped_actions_array";
            return true;
        }
    }
    *note = "unsupported_root_shape";
    return false;
}

bool type_matches(const json& instance, const std::string& type) {
    if (type == "object") return instance.is_object();
    if (type == "array") return instance.is_array();
    if (type == "string") return instance.is_string();
    if (type == "integer") return instance.is_number_integer();
    if (type == "number") return instance.is_number();
    if (type == "boolean") return instance.is_boolean();
    if (type == "null") return instance.is_null();
    return false;
}

bool validate_schema(const json& schema, const json& instance, const std::string& path, std::string* error);

bool validate_alternatives(const json& alternatives, const json& instance, const std::string& path,
                           bool require_exactly_one, std::string* error) {
    size_t matches = 0;
    std::string first_error;
    for (const auto& candidate : alternatives) {
        std::string candidate_error;
        if (validate_schema(candidate, instance, path, &candidate_error)) ++matches;
        else if (first_error.empty()) first_error = candidate_error;
    }
    if ((require_exactly_one && matches == 1) || (!require_exactly_one && matches >= 1)) return true;
    std::ostringstream out;
    out << path << ":" << (require_exactly_one ? "oneOf" : "anyOf") << "_matches=" << matches;
    if (!first_error.empty()) out << ";first=" << first_error;
    *error = out.str();
    return false;
}

bool validate_schema(const json& schema, const json& instance, const std::string& path, std::string* error) {
    if (!schema.is_object()) {
        *error = path + ":schema_not_object";
        return false;
    }
    if (schema.contains("oneOf")) {
        return validate_alternatives(schema.at("oneOf"), instance, path, true, error);
    }
    if (schema.contains("anyOf")) {
        return validate_alternatives(schema.at("anyOf"), instance, path, false, error);
    }
    if (schema.contains("const") && instance != schema.at("const")) {
        *error = path + ":const_mismatch";
        return false;
    }
    if (schema.contains("enum")) {
        bool found = false;
        for (const auto& allowed : schema.at("enum")) {
            if (instance == allowed) { found = true; break; }
        }
        if (!found) {
            *error = path + ":enum_mismatch";
            return false;
        }
    }
    if (schema.contains("type")) {
        if (schema.at("type").is_string()) {
            if (!type_matches(instance, schema.at("type").get<std::string>())) {
                *error = path + ":type_mismatch";
                return false;
            }
        } else if (schema.at("type").is_array()) {
            bool matched = false;
            for (const auto& value : schema.at("type")) {
                if (value.is_string() && type_matches(instance, value.get<std::string>())) matched = true;
            }
            if (!matched) {
                *error = path + ":type_mismatch";
                return false;
            }
        }
    }
    if (instance.is_object()) {
        if (schema.contains("required")) {
            for (const auto& key : schema.at("required")) {
                if (!instance.contains(key.get<std::string>())) {
                    *error = path + ":missing_required:" + key.get<std::string>();
                    return false;
                }
            }
        }
        const json properties = schema.value("properties", json::object());
        const bool allow_extra = schema.value("additionalProperties", true);
        for (auto it = instance.begin(); it != instance.end(); ++it) {
            if (properties.contains(it.key())) {
                if (!validate_schema(properties.at(it.key()), it.value(), path + "." + it.key(), error)) return false;
            } else if (!allow_extra) {
                *error = path + ":additional_property:" + it.key();
                return false;
            }
        }
    }
    if (instance.is_array()) {
        if (schema.contains("minItems") && instance.size() < schema.at("minItems").get<size_t>()) {
            *error = path + ":minItems";
            return false;
        }
        if (schema.contains("maxItems") && instance.size() > schema.at("maxItems").get<size_t>()) {
            *error = path + ":maxItems";
            return false;
        }
        if (schema.contains("items")) {
            for (size_t index = 0; index < instance.size(); ++index) {
                if (!validate_schema(schema.at("items"), instance[index], path + "[" + std::to_string(index) + "]", error)) return false;
            }
        }
    }
    if (instance.is_number()) {
        const double number = instance.get<double>();
        if (schema.contains("minimum") && number < schema.at("minimum").get<double>()) {
            *error = path + ":minimum";
            return false;
        }
        if (schema.contains("maximum") && number > schema.at("maximum").get<double>()) {
            *error = path + ":maximum";
            return false;
        }
    }
    if (instance.is_string()) {
        const auto& value = instance.get_ref<const std::string&>();
        if (schema.contains("minLength") && value.size() < schema.at("minLength").get<size_t>()) {
            *error = path + ":minLength";
            return false;
        }
    }
    return true;
}

struct Generation {
    std::string text;
    double milliseconds = 0.0;
    int return_code = 0;
    RKLLMPerfStat perf = {};
    bool has_perf = false;
};

Generation generate(const std::string& prompt) {
    RKLLMInput input;
    std::memset(&input, 0, sizeof(input));
    input.input_type = RKLLM_INPUT_PROMPT;
    input.role = "user";
    input.enable_thinking = false;
    input.prompt_input = const_cast<char*>(prompt.c_str());

    RKLLMInferParam infer;
    std::memset(&infer, 0, sizeof(infer));
    infer.mode = RKLLM_INFER_GENERATE;
    infer.keep_history = 0;

    g_generated.clear();
    g_has_perf = false;
    const auto start = std::chrono::steady_clock::now();
    const int ret = rkllm_run(g_handle, &input, &infer, nullptr);
    const auto end = std::chrono::steady_clock::now();
    const double elapsed = std::chrono::duration<double, std::milli>(end - start).count();
    Generation output;
    output.text = g_generated;
    output.milliseconds = g_has_perf
        ? static_cast<double>(g_perf.prefill_time_ms + g_perf.generate_time_ms)
        : elapsed;
    output.return_code = ret;
    output.perf = g_perf;
    output.has_perf = g_has_perf;
    return output;
}

std::string correction_prompt(const std::string& original, const std::string& raw, const std::string& error) {
    std::string bounded_raw = raw;
    if (bounded_raw.size() > 2000) bounded_raw.resize(2000);
    return original
        + " [格式纠正] 上一次输出未执行，因为不符合规定的Structured Output。错误=" + error
        + "。上一次输出=" + bounded_raw
        + "。请重新回答；只能输出一个符合output_protocol的JSON对象，不要解释，不要Markdown。 [助手]";
}

std::string structured_prompt(const std::string& original, const json& schema) {
    return original
        + " [强制结构输出] 不要复述输入，不要Markdown，不要解释。"
        + "只填写下列JSON Schema允许的字段，并只输出一个JSON值。JSON_SCHEMA="
        + schema.dump() + " [助手]";
}

void emit_error(const std::string& id, double milliseconds, const std::string& code,
                const std::string& detail, const std::string& raw) {
    json body = {{"code", code}, {"detail", detail}, {"raw_output", raw}};
    std::cout << kError << '\t' << id << '\t' << milliseconds << '\t' << body.dump() << '\n';
}

void emit_audit(const std::string& id, const std::string& first_raw,
                const std::string& accepted_raw, bool first_raw_schema_valid,
                bool accepted_raw_schema_valid, bool normalization_used,
                bool retry_used, const std::string& normalization_note) {
    json body = {
        {"first_raw_output", first_raw},
        {"accepted_raw_output", accepted_raw},
        {"first_raw_schema_valid", first_raw_schema_valid},
        {"accepted_raw_schema_valid", accepted_raw_schema_valid},
        {"normalization_used", normalization_used},
        {"normalization_note", normalization_note},
        {"retry_used", retry_used},
    };
    std::cout << kAudit << '\t' << id << '\t' << body.dump() << '\n';
}

void emit_perf(const std::string& id, int generation_pass, const Generation& generation) {
    json body = {{"generation_pass", generation_pass}, {"available", generation.has_perf}};
    if (generation.has_perf) {
        const auto& perf = generation.perf;
        const double prefill_tps = perf.prefill_time_ms > 0.0f
            ? static_cast<double>(perf.prefill_tokens) * 1000.0 / perf.prefill_time_ms : 0.0;
        const double generation_tps = perf.generate_time_ms > 0.0f
            ? static_cast<double>(perf.generate_tokens) * 1000.0 / perf.generate_time_ms : 0.0;
        body.update({
            {"prefill_time_ms", perf.prefill_time_ms},
            {"prefill_tokens", perf.prefill_tokens},
            {"prefill_tokens_per_second", prefill_tps},
            {"generate_time_ms", perf.generate_time_ms},
            {"generate_tokens", perf.generate_tokens},
            {"generate_tokens_per_second", generation_tps},
            {"total_inference_time_ms", perf.prefill_time_ms + perf.generate_time_ms},
            {"memory_usage_mb", perf.memory_usage_mb},
        });
    }
    std::cout << kPerf << '\t' << id << '\t' << body.dump() << '\n';
}

}  // namespace

int main(int argc, char** argv) {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    std::cout.setf(std::ios::unitbuf);
    std::cerr.setf(std::ios::unitbuf);

    if (argc != 5) {
        std::cerr << "Usage: " << argv[0] << " model_path max_new_tokens max_context_len schema_json_path\n";
        return 1;
    }

    json schema;
    try {
        schema = json::parse(read_file(argv[4]));
    } catch (const std::exception& exc) {
        std::cerr << "schema_load_failed:" << exc.what() << '\n';
        return 2;
    }

    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    RKLLMParam param = rkllm_createDefaultParam();
    param.model_path = argv[1];
    param.max_new_tokens = std::atoi(argv[2]);
    param.max_context_len = std::atoi(argv[3]);
    param.top_k = 1;
    param.top_p = 1.0f;
    param.temperature = 0.1f;
    param.repeat_penalty = 1.12f;
    param.frequency_penalty = 0.0f;
    param.presence_penalty = 0.0f;
    param.skip_special_token = true;
    param.extend_param.base_domain_id = 0;
    param.extend_param.embed_flash = 1;

    RKLLMCallback callback = {};
    callback.result_callback = result_callback;
    const int init_ret = rkllm_init(&g_handle, &param, &callback);
    if (init_ret != 0) {
        std::cerr << "rkllm_init_failed:" << init_ret << '\n';
        return 3;
    }
    std::cout << kReady << '\n';

    std::string line;
    while (std::getline(std::cin, line)) {
        if (line == "QUIT") break;
        const auto tab = line.find('\t');
        if (tab == std::string::npos) {
            emit_error("unknown", 0.0, "wire_protocol_error", "missing_tab", line);
            continue;
        }
        const std::string id = line.substr(0, tab);
        const std::string prompt = line.substr(tab + 1);

        const std::string constrained_prompt = structured_prompt(prompt, schema);
        Generation first = generate(constrained_prompt);
        emit_perf(id, 1, first);
        if (first.return_code != 0) {
            emit_error(id, first.milliseconds, "rkllm_run_failed", std::to_string(first.return_code), first.text);
            continue;
        }
        json parsed;
        json candidate;
        std::string error;
        std::string coercion;
        const bool first_parsed = extract_json_value(first.text, &parsed, &error);
        json first_exact;
        std::string raw_validation_error;
        const bool first_raw_valid = parse_exact_json_value(first.text, &first_exact)
            && validate_schema(schema, first_exact, "$", &raw_validation_error);
        const bool first_normalized = first_parsed
            && coerce_protocol_shape(schema, parsed, &candidate, &coercion)
            && validate_schema(schema, candidate, "$", &error);
        if (first_normalized) {
            const bool normalization_used = !first_raw_valid || !coercion.empty();
            emit_audit(id, first.text, first.text, first_raw_valid, first_raw_valid,
                       normalization_used, false, coercion);
            std::cout << kDiagnostic << '\t' << id
                      << "\tgeneration_pass=1\traw_schema_valid=" << (first_raw_valid ? 1 : 0)
                      << "\tnormalization_used=" << (normalization_used ? 1 : 0)
                      << "\tretry_used=0\tcoercion=" << coercion << "\n";
            std::cout << kResult << '\t' << id << '\t' << first.milliseconds << '\t' << candidate.dump() << '\n';
            continue;
        }

        std::cout << kDiagnostic << '\t' << id
                  << "\tgeneration_pass=1\traw_schema_valid=" << (first_raw_valid ? 1 : 0)
                  << "\tnormalization_used=0\tretry_used=1\terror=" << error << '\n';
        Generation second = generate(correction_prompt(constrained_prompt, first.text, error));
        emit_perf(id, 2, second);
        const double total_ms = first.milliseconds + second.milliseconds;
        if (second.return_code != 0) {
            emit_error(id, total_ms, "rkllm_retry_failed", std::to_string(second.return_code), second.text);
            continue;
        }
        json corrected_parsed;
        json corrected;
        std::string second_error;
        std::string second_coercion;
        const bool second_parsed = extract_json_value(second.text, &corrected_parsed, &second_error);
        json second_exact;
        std::string second_raw_validation_error;
        const bool second_raw_valid = parse_exact_json_value(second.text, &second_exact)
            && validate_schema(schema, second_exact, "$", &second_raw_validation_error);
        if (!second_parsed
            || !coerce_protocol_shape(schema, corrected_parsed, &corrected, &second_coercion)
            || !validate_schema(schema, corrected, "$", &second_error)) {
            emit_audit(id, first.text, second.text, first_raw_valid, second_raw_valid,
                       false, true, second_coercion);
            emit_error(id, total_ms, "schema_validation_failed", second_error, second.text);
            continue;
        }
        const bool normalization_used = !second_raw_valid || !second_coercion.empty();
        emit_audit(id, first.text, second.text, first_raw_valid, second_raw_valid,
                   normalization_used, true, second_coercion);
        std::cout << kDiagnostic << '\t' << id
                  << "\tgeneration_pass=2\traw_schema_valid=" << (second_raw_valid ? 1 : 0)
                  << "\tnormalization_used=" << (normalization_used ? 1 : 0)
                  << "\tretry_used=1\tcoercion=" << second_coercion << "\n";
        std::cout << kResult << '\t' << id << '\t' << total_ms << '\t' << corrected.dump() << '\n';
    }

    destroy_model();
    return 0;
}
