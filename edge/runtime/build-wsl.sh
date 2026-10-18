#!/usr/bin/env bash
set -euo pipefail

runtime_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build_dir="${runtime_dir}/build"
install_dir="${runtime_dir}/install"

: "${RKLLM_API_PATH:?Set RKLLM_API_PATH to .../rkllm-runtime/Linux/librkllm_api}"
CROSS_PREFIX="${CROSS_PREFIX:-aarch64-none-linux-gnu}"
CXX_BIN="${CXX:-${CROSS_PREFIX}-g++}"

cmake -S "${runtime_dir}" -B "${build_dir}" \
  -DCMAKE_SYSTEM_NAME=Linux \
  -DCMAKE_SYSTEM_PROCESSOR=aarch64 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER="${CXX_BIN}" \
  -DCMAKE_INSTALL_PREFIX="${install_dir}" \
  -DRKLLM_API_PATH="${RKLLM_API_PATH}" \
  -DNLOHMANN_JSON_INCLUDE_DIR="${NLOHMANN_JSON_INCLUDE_DIR:-/usr/include}"
cmake --build "${build_dir}" --parallel
cmake --install "${build_dir}"

file "${install_dir}/bin/edgehome_rkllm_persistent"
file "${install_dir}/bin/rkllm_structured_persistent"
sha256sum "${install_dir}/bin/edgehome_rkllm_persistent" \
          "${install_dir}/bin/rkllm_structured_persistent"
