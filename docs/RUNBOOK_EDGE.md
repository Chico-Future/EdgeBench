# Optional Rockchip device adapter

The `edge/` adapter supports a Rockchip RKLLM runtime integration. It is optional: API/server evaluation does not require it. Model weights, converted models, vendor headers, and runtime libraries are not distributed here.

The bundled persistent launcher uses a Qwen3-style non-thinking chat template. Do not assume it supports every model family. Verify the template, tokenizer, conversion, and vendor runtime compatibility for your model before running an evaluation.

Build prerequisites and the CMake interface are in [edge/runtime](../edge/runtime/). The runtime requires external Rockchip RKLLM headers and libraries and a compatible device/toolchain. Use `python3 -m edge.run_state_given --help` and `python3 -m edge.run_state_seeking --help` for required paths and budgets.

Hardware execution has not been validated by the offline CI checks. Device availability, conversion correctness, and runtime behavior must be checked on the target board. No device performance claims are made by this release.
