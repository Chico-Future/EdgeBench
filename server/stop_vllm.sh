#!/usr/bin/env bash
set -euo pipefail

: "${PID_FILE:?set PID_FILE to the file written by start_vllm.sh}"
if [[ ! -f "${PID_FILE}" ]]; then
  echo "PID file not found: ${PID_FILE}" >&2
  exit 1
fi
pid="$(cat "${PID_FILE}")"
if kill -0 "${pid}" 2>/dev/null; then
  kill "${pid}"
  wait "${pid}" 2>/dev/null || true
fi
rm -f "${PID_FILE}"
