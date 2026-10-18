#!/usr/bin/env bash
set -euo pipefail

: "${MODEL_PATH:?set MODEL_PATH to the Hugging Face model directory}"
: "${SERVED_MODEL_NAME:?set SERVED_MODEL_NAME to the stable experiment model id}"
PORT="${PORT:-8000}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-16384}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.80}"
DTYPE="${DTYPE:-auto}"
LOG_DIR="${LOG_DIR:-logs/vllm}"
PID_FILE="${PID_FILE:-${LOG_DIR}/${SERVED_MODEL_NAME}.pid}"
TEXT_ONLY="${TEXT_ONLY:-1}"
mkdir -p "${LOG_DIR}"

export VLLM_USE_FLASHINFER_SAMPLER="${VLLM_USE_FLASHINFER_SAMPLER:-0}"
args=(
  --model "${MODEL_PATH}"
  --served-model-name "${SERVED_MODEL_NAME}"
  --host 127.0.0.1
  --port "${PORT}"
  --max-model-len "${MAX_MODEL_LEN}"
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}"
  --dtype "${DTYPE}"
  --generation-config vllm
)
if [[ "${TEXT_ONLY}" == "1" ]]; then
  args+=(--language-model-only)
fi
if [[ -n "${VLLM_EXTRA_ARGS:-}" ]]; then
  # Deliberately allow shell-style extra CLI arguments supplied by the experiment operator.
  read -r -a extra <<< "${VLLM_EXTRA_ARGS}"
  args+=("${extra[@]}")
fi

nohup python -m vllm.entrypoints.openai.api_server "${args[@]}" \
  > "${LOG_DIR}/${SERVED_MODEL_NAME}.log" 2>&1 &
echo $! > "${PID_FILE}"
echo "vLLM PID=$(cat "${PID_FILE}") log=${LOG_DIR}/${SERVED_MODEL_NAME}.log"
