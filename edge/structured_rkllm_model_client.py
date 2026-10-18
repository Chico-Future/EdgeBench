from __future__ import annotations

import json
import math
import os
import queue
import re
import subprocess
import threading
import time
from typing import Any

from .board_metrics import BoardMetricsSampler


READY_MARKER = "__TEXT_LLM_READY__"
RESULT_MARKER = "__TEXT_LLM_RESULT__"
ERROR_MARKER = "__TEXT_LLM_ERROR__"
DIAGNOSTIC_MARKER = "__STRUCTURED_DIAGNOSTIC__"
AUDIT_MARKER = "__STRUCTURED_AUDIT__"
PERF_MARKER = "__RKLLM_PERF__"


class StructuredOutputRejected(ValueError):
    def __init__(self, message: str, telemetry: dict[str, Any]):
        super().__init__(message)
        self.telemetry = telemetry


class RKLLMRuntimeError(RuntimeError):
    def __init__(self, message: str, telemetry: dict[str, Any]):
        super().__init__(message)
        self.telemetry = telemetry


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char == "{":
            try:
                value, _ = decoder.raw_decode(cleaned[index:])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
    raise ValueError("模型输出中没有可解析的JSON对象")


def aggregate_rkllm_perf(passes: list[dict[str, Any]]) -> dict[str, Any]:
    available = [item for item in passes if item.get("available")]
    if not available:
        return {"available": False, "generation_passes": len(passes)}
    prefill_ms = sum(float(item.get("prefill_time_ms", 0)) for item in available)
    generate_ms = sum(float(item.get("generate_time_ms", 0)) for item in available)
    prefill_tokens = sum(int(item.get("prefill_tokens", 0)) for item in available)
    generate_tokens = sum(int(item.get("generate_tokens", 0)) for item in available)
    return {
        "available": True,
        "generation_passes": len(available),
        "prefill_time_ms": round(prefill_ms, 3),
        "prefill_tokens": prefill_tokens,
        "prefill_tokens_per_second": round(prefill_tokens * 1000.0 / prefill_ms, 3) if prefill_ms else None,
        "generate_time_ms": round(generate_ms, 3),
        "generate_tokens": generate_tokens,
        "generate_tokens_per_second": round(generate_tokens * 1000.0 / generate_ms, 3) if generate_ms else None,
        "total_inference_time_ms": round(prefill_ms + generate_ms, 3),
        "peak_memory_usage_mb": round(max(float(item.get("memory_usage_mb", 0)) for item in available), 3),
    }


class TokenCounter:
    """提供本地tokenizer时精确计数，否则给出带安全系数的估算值。"""

    def __init__(self, tokenizer_path: str | None = None, safety_factor: float = 1.25):
        self.safety_factor = safety_factor
        self.tokenizer = None
        self.method = "heuristic"
        if tokenizer_path:
            try:
                from transformers import AutoTokenizer
            except ImportError as exc:
                raise RuntimeError("使用--tokenizer-path需要安装transformers") from exc
            self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True, trust_remote_code=True)
            self.method = "qwen_tokenizer"

    def count(self, text: str) -> int:
        if self.tokenizer is not None:
            return len(self.tokenizer.encode(text, add_special_tokens=True))
        cjk = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
        ascii_like = len(text) - cjk
        return max(1, math.ceil((cjk * 1.15 + ascii_like / 3.0) * self.safety_factor))


class PersistentRKLLMClient:
    def __init__(self, binary: str, model_path: str, max_new_tokens: int, max_context_len: int,
                 ld_library_path: str, startup_timeout: float = 120.0, request_timeout: float = 300.0,
                 structured_schema: str | None = None, collect_board_metrics: bool = True,
                 metrics_sample_interval_ms: int = 100):
        env = os.environ.copy()
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = ld_library_path + ((":" + existing) if existing else "")
        self.request_timeout = request_timeout
        self.collect_board_metrics = collect_board_metrics
        self.metrics_sample_interval_ms = metrics_sample_interval_ms
        startup_started = time.perf_counter()
        command = [binary, model_path, str(max_new_tokens), str(max_context_len)]
        if structured_schema:
            command.append(structured_schema)
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
        )
        startup_sampler = (
            BoardMetricsSampler(self.process.pid, self.metrics_sample_interval_ms)
            if self.collect_board_metrics
            else None
        )
        if startup_sampler is not None:
            startup_sampler.start()
        # Do not combine select() with TextIOWrapper.readline().  readline() may
        # buffer several runtime records while select() only observes the kernel
        # pipe, which can make already-buffered audit/result lines appear to time
        # out.  A single reader thread drains stdout continuously into a queue.
        self._stdout_queue: queue.Queue[str | None] = queue.Queue()
        self._stdout_reader_error: BaseException | None = None
        self._stdout_reader = threading.Thread(
            target=self._pump_stdout,
            name="rkllm-stdout-reader",
            daemon=True,
        )
        self._stdout_reader.start()
        self.startup_log: list[str] = []
        deadline = time.monotonic() + startup_timeout
        try:
            while True:
                line = self._readline(max(0.1, deadline - time.monotonic()))
                self.startup_log.append(line.rstrip("\r\n"))
                if READY_MARKER in line:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("等待__TEXT_LLM_READY__超时")
        except Exception as exc:
            self.startup_board_metrics = (
                startup_sampler.stop() if startup_sampler is not None else None
            )
            detail = " | ".join(item for item in self.startup_log if item)
            self.close()
            raise RuntimeError(f"RKLLM启动失败: {exc}; startup_log={detail}") from exc
        self.startup_wall_latency_ms = round(
            (time.perf_counter() - startup_started) * 1000, 3
        )
        self.startup_board_metrics = (
            startup_sampler.stop() if startup_sampler is not None else None
        )

    @staticmethod
    def render_messages(messages: list[dict[str, str]]) -> str:
        role_names = {"system": "系统", "user": "用户", "assistant": "助手", "tool": "工具"}
        parts = [f"[{role_names.get(item['role'], item['role'])}]{item['content']}" for item in messages]
        return " ".join(parts).replace("\t", " ").replace("\r", " ").replace("\n", " ") + " [助手]"

    def _pump_stdout(self) -> None:
        if self.process.stdout is None:
            self._stdout_reader_error = RuntimeError("stdout未建立")
            self._stdout_queue.put(None)
            return
        try:
            for line in self.process.stdout:
                self._stdout_queue.put(line)
        except BaseException as exc:  # surfaced to the consumer thread
            self._stdout_reader_error = exc
        finally:
            self._stdout_queue.put(None)

    def _readline(self, timeout: float) -> str:
        try:
            line = self._stdout_queue.get(timeout=max(0.0, timeout))
        except queue.Empty as exc:
            returncode = self.process.poll()
            if returncode is not None:
                raise RuntimeError(f"RKLLM子进程已退出: {returncode}") from exc
            raise TimeoutError("等待RKLLM输出超时") from exc
        if line is None:
            detail = (
                f"; reader_error={self._stdout_reader_error!r}"
                if self._stdout_reader_error is not None
                else ""
            )
            raise RuntimeError(
                f"RKLLM输出流已关闭: returncode={self.process.poll()}{detail}"
            )
        return line

    @staticmethod
    def _parse_wire_line(line: str, marker: str) -> tuple[str, float, str]:
        rest = line[line.index(marker) + len(marker):].lstrip(" \t")
        parts = rest.rstrip("\r\n").split("\t", 2)
        if len(parts) < 3:
            parts = re.split(r"\s+", rest.rstrip("\r\n"), maxsplit=2)
        if len(parts) != 3:
            raise ValueError(f"无法解析RKLLM结果行: {line!r}")
        return parts[0], float(parts[1]), parts[2]

    def complete_prompt(self, prompt: str, request_id: str) -> tuple[str, dict[str, Any]]:
        if self.process.stdin is None:
            raise RuntimeError("stdin未建立")
        safe_id = str(request_id).replace("\t", "_").replace("\n", "_")
        wire_prompt = prompt.replace("\t", " ").replace("\r", " ").replace("\n", " ")
        start = time.perf_counter()
        sampler = (BoardMetricsSampler(self.process.pid, self.metrics_sample_interval_ms)
                   if self.collect_board_metrics else None)
        if sampler is not None:
            sampler.start()
        sampled_metrics: dict[str, Any] | None = None

        def stop_sampler() -> dict[str, Any] | None:
            nonlocal sampled_metrics
            if sampler is not None and sampled_metrics is None:
                sampled_metrics = sampler.stop()
            return sampled_metrics

        try:
            self.process.stdin.write(f"{safe_id}\t{wire_prompt}\n")
            self.process.stdin.flush()
        except Exception:
            stop_sampler()
            raise
        logs = []
        perf_passes: list[dict[str, Any]] = []
        structured_first_pass = None
        structured_retry_used = False
        accepted_generation_pass = None
        audit: dict[str, Any] = {}

        def build_telemetry(inference_ms: float) -> dict[str, Any]:
            board_metrics = stop_sampler()
            first_raw_valid = audit.get("first_raw_schema_valid")
            first_pass = structured_first_pass
            if first_pass is None and isinstance(first_raw_valid, bool):
                first_pass = first_raw_valid and not bool(audit.get("retry_used"))
            return {"inference_ms": inference_ms,
                    "wall_latency_ms": round((time.perf_counter() - start) * 1000, 3),
                    "runtime_log": list(logs),
                    "structured_first_pass": first_pass,
                    "structured_retry_used": structured_retry_used,
                    "accepted_generation_pass": accepted_generation_pass,
                    "first_raw_output": audit.get("first_raw_output", ""),
                    "accepted_raw_output": audit.get("accepted_raw_output", ""),
                    "first_raw_schema_valid": first_raw_valid,
                    "accepted_raw_schema_valid": audit.get("accepted_raw_schema_valid"),
                    "structured_normalization_used": audit.get("normalization_used", False),
                    "structured_normalization_note": audit.get("normalization_note", ""),
                    "rkllm_perf_passes": list(perf_passes),
                    "rkllm_perf": aggregate_rkllm_perf(perf_passes),
                    "board_metrics": board_metrics}
        request_deadline = time.monotonic() + self.request_timeout
        while True:
            try:
                remaining = request_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("等待RKLLM完整响应超时")
                line = self._readline(remaining)
            except Exception as exc:
                raise RKLLMRuntimeError(str(exc), build_telemetry(0.0)) from exc
            stripped = line.rstrip("\r\n")
            if PERF_MARKER in line:
                rest = line[line.index(PERF_MARKER) + len(PERF_MARKER):].lstrip(" \t")
                parts = rest.rstrip("\r\n").split("\t", 1)
                if len(parts) == 2 and parts[0] == safe_id:
                    try:
                        perf_passes.append(json.loads(parts[1]))
                    except json.JSONDecodeError:
                        logs.append(stripped)
                else:
                    logs.append(stripped)
                continue
            if DIAGNOSTIC_MARKER in line:
                logs.append(stripped)
                if "generation_pass=1" in line:
                    accepted_generation_pass = 1
                elif "generation_pass=2" in line:
                    accepted_generation_pass = 2
                if "first_pass=1" in line:
                    structured_first_pass = True
                elif "first_pass=0" in line:
                    structured_first_pass = False
                structured_retry_used = "retry_used=1" in line
                continue
            if AUDIT_MARKER in line:
                rest = line[line.index(AUDIT_MARKER) + len(AUDIT_MARKER):].lstrip(" \t")
                parts = rest.rstrip("\r\n").split("\t", 1)
                if len(parts) == 2 and parts[0] == safe_id:
                    audit = json.loads(parts[1])
                else:
                    logs.append(stripped)
                continue
            if ERROR_MARKER in line:
                returned_id, inference_ms, payload = self._parse_wire_line(line, ERROR_MARKER)
                if returned_id != safe_id:
                    logs.append(stripped)
                    continue
                try:
                    error_body = json.loads(payload)
                except json.JSONDecodeError:
                    error_body = {}
                if not audit and isinstance(error_body.get("raw_output"), str):
                    audit["first_raw_output"] = error_body["raw_output"]
                    audit["accepted_raw_output"] = error_body["raw_output"]
                    audit["first_raw_schema_valid"] = False
                    audit["accepted_raw_schema_valid"] = False
                raise StructuredOutputRejected(f"structured_output_rejected: {payload}",
                                               build_telemetry(inference_ms))
            if RESULT_MARKER not in line:
                logs.append(stripped); continue
            returned_id, inference_ms, answer = self._parse_wire_line(line, RESULT_MARKER)
            if returned_id != safe_id:
                logs.append(stripped); continue
            if not audit:
                audit.update({"first_raw_output": answer, "accepted_raw_output": answer})
            return answer, build_telemetry(inference_ms)

    def close(self) -> None:
        if self.process.poll() is None and self.process.stdin is not None:
            try:
                self.process.stdin.write("QUIT\n"); self.process.stdin.flush(); self.process.wait(timeout=10)
            except Exception:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        self._stdout_reader.join(timeout=2)
        for stream in (self.process.stdin, self.process.stdout):
            if stream is not None and not stream.closed:
                stream.close()

    def __enter__(self): return self
    def __exit__(self, *_): self.close()
