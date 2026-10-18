# RKLLM board runtime

本目录保存论文端侧实验实际使用的两个 RKLLM persistent launcher 源码；不保存模型、
`librkllmrt.so` 或交叉编译产物。

| 二进制 | Profile | 行为 |
|---|---|---|
| `edgehome_rkllm_persistent` | `P0_prompt_only` | Qwen3 non-thinking Chat Template；无 Schema 注入、无 Native Function Tools |
| `rkllm_structured_persistent` | `P2_prompt_schema_repair1` | 完整 JSON Schema 拼入 Prompt；本地结构归一化；最多一次格式纠正 |

两者均以持久进程方式加载模型，按 case 隔离 KV cache，并输出机器可读的延迟、
prefill/decode token、吞吐和 RKLLM 内存指标。Python 端另从 Linux `/proc`、`/sys`
采集 RSS、系统可用内存、温度、devfreq 和板上可用功耗传感器。

## WSL2 交叉编译

```bash
cd /mnt/d/AI端侧/edgehome_agentbench/EdgeHome_Unified_Eval_v2/edge/runtime
export PATH="$HOME/opts/gcc-arm-10.2-2020.11-x86_64-aarch64-none-linux-gnu/bin:$PATH"
export RKLLM_API_PATH=/mnt/e/ai_software/rkllm/rknn-llm-release-v1.3.0/rkllm-runtime/Linux/librkllm_api
# 默认以低优先级读取 /usr/include/nlohmann/json.hpp；也可指定其他 include 根目录：
# export NLOHMANN_JSON_INCLUDE_DIR=/path/to/include
bash build-wsl.sh
```

产物位于 `edge/runtime/install/bin/`。将所需二进制及与模型转换版本匹配的
`librkllmrt.so` 上传开发板。16K 模型必须由支持 16384 context 的 toolkit 转换；
模型、runtime、API 头文件和板上驱动的兼容性仍由 RKLLM runtime 在加载时校验。

端侧任务运行和统一评分见仓库根目录 `EDGE_HANDOFF.md`。不要使用数据集旧目录中的
评分脚本；论文结果只认 `scoring/unified_scorer.py`。
