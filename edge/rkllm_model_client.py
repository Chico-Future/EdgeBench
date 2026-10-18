from __future__ import annotations

import base64
import json
import math
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from .board_metrics import BoardMetricsSampler


READY_MARKER = "__EDGEHOME_READY__"
RESULT_MARKER = "__EDGEHOME_RESULT__"
RESET_MARKER = "__EDGEHOME_RESET__"
PROTOCOL_ERROR_MARKER = "__EDGEHOME_PROTOCOL_ERROR__"


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


def render_qwen3_messages(messages: list[dict[str, str]]) -> str:
    """Mirror the exact Qwen3 non-thinking template installed by the launcher."""
    rendered = []
    for message in messages:
        role = message["role"]
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"不支持的消息角色: {role}")
        rendered.append(f"<|im_start|>{role}\n{message['content']}<|im_end|>\n")
    rendered.append("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    return "".join(rendered)


class TokenCounter:
    """Use the exact local tokenizer when available, otherwise be conservative."""

    def __init__(self, tokenizer_path: str | None = None, safety_factor: float = 1.25):
        self.safety_factor = safety_factor
        self.tokenizer = None
        self.method = "heuristic_qwen3_template"
        if tokenizer_path:
            try:
                from tokenizers import Tokenizer
            except ImportError as exc:
                raise RuntimeError("使用--tokenizer-path需要安装轻量依赖tokenizers") from exc
            tokenizer_file = Path(tokenizer_path) / "tokenizer.json"
            if not tokenizer_file.is_file():
                raise RuntimeError(f"未找到tokenizer.json: {tokenizer_file}")
            self.tokenizer = Tokenizer.from_file(str(tokenizer_file))
            self.method = "qwen_tokenizer_json_rkllm13_calibrated"

    def count(self, text: str) -> int:
        if self.tokenizer is not None:
            return len(self.tokenizer.encode(text, add_special_tokens=False).ids)
        cjk = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
        ascii_like = len(text) - cjk
        return max(1, math.ceil((cjk * 1.15 + ascii_like / 3.0) * self.safety_factor))

    def count_messages(self, messages: list[dict[str, str]]) -> int:
        count = self.count(render_qwen3_messages(messages))
        if self.tokenizer is not None:
            # RKLLM Runtime 1.3 retains two non-text control positions for every
            # completed assistant generation. They are present in KV-cache
            # accounting but absent from the callback text reconstructed here.
            count += 2 * sum(message["role"] == "assistant" for message in messages)
        return count


class PersistentRKLLMClient:
    """Client for edgehome_rkllm_persistent's Base64 line protocol."""

    def __init__(
        self,
        binary: str,
        model_path: str,
        max_new_tokens: int,
        max_context_len: int,
        ld_library_path: str,
        system_prompt: str,
        startup_timeout: float = 120.0,
        request_timeout: float = 300.0,
        collect_board_metrics: bool = True,
        metrics_sample_interval_ms: int = 100,
    ):
        env = os.environ.copy()
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = ld_library_path + ((":" + existing) if existing else "")
        self.request_timeout = request_timeout
        self.collect_board_metrics = collect_board_metrics
        self.metrics_sample_interval_ms = metrics_sample_interval_ms
        startup_started = time.perf_counter()
        startup_sampler: BoardMetricsSampler | None = None
        prompt_file = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="edgehome_system_", suffix=".txt", delete=False
        )
        try:
            prompt_file.write(system_prompt)
            prompt_file.flush()
        finally:
            prompt_file.close()
        self._system_prompt_path = Path(prompt_file.name)
        try:
            self.process = subprocess.Popen(
                [binary, model_path, str(max_new_tokens), str(max_context_len), str(self._system_prompt_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
            if self.collect_board_metrics:
                startup_sampler = BoardMetricsSampler(
                    self.process.pid, self.metrics_sample_interval_ms
                )
                startup_sampler.start()
            self._stdout_queue: queue.Queue[str | None] = queue.Queue()
            self._stdout_reader_error: BaseException | None = None
            self._stdout_reader = threading.Thread(
                target=self._pump_stdout,
                name="edgehome-rkllm-stdout",
                daemon=True,
            )
            self._stdout_reader.start()
            self.startup_log: list[str] = []
            deadline = time.monotonic() + startup_timeout
            while True:
                line = self._readline(max(0.1, deadline - time.monotonic()))
                self.startup_log.append(line.rstrip("\r\n"))
                if READY_MARKER in line:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"等待{READY_MARKER}超时")
            self.startup_wall_latency_ms = round(
                (time.perf_counter() - startup_started) * 1000, 3
            )
            self.startup_board_metrics = (
                startup_sampler.stop() if startup_sampler is not None else None
            )
        except Exception as exc:
            if startup_sampler is not None:
                self.startup_board_metrics = startup_sampler.stop()
            startup_tail = "\n".join(getattr(self, "startup_log", [])[-80:])
            process = getattr(self, "process", None)
            return_code = process.poll() if process is not None else None
            if process is not None and return_code is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            self._delete_prompt_file()
            detail = f"RKLLM启动失败，returncode={return_code}"
            if startup_tail:
                detail += f"\n--- startup log ---\n{startup_tail}"
            raise RuntimeError(detail) from exc

    @staticmethod
    def render_messages(messages: list[dict[str, str]]) -> str:
        return render_qwen3_messages(messages)

    @staticmethod
    def _safe_request_id(request_id: str) -> str:
        return str(request_id).replace("\t", "_").replace("\r", "_").replace("\n", "_")

    def _pump_stdout(self) -> None:
        try:
            if self.process.stdout is None:
                raise RuntimeError("stdout未建立")
            for line in self.process.stdout:
                self._stdout_queue.put(line)
        except BaseException as exc:
            self._stdout_reader_error = exc
        finally:
            self._stdout_queue.put(None)

    def _readline(self, timeout: float) -> str:
        try:
            line = self._stdout_queue.get(timeout=max(0.001, timeout))
        except queue.Empty as exc:
            if self.process.poll() is not None:
                raise RuntimeError(f"RKLLM子进程已退出: {self.process.returncode}") from exc
            raise TimeoutError("等待RKLLM输出超时") from exc
        if line is None:
            if self._stdout_reader_error is not None:
                raise RuntimeError("RKLLM输出读取线程失败") from self._stdout_reader_error
            raise RuntimeError(f"RKLLM输出流已关闭: returncode={self.process.poll()}")
        return line

    @staticmethod
    def _parse_perf(logs: list[str]) -> dict[str, Any]:
        line = next((item for item in reversed(logs) if item.startswith("[edgehome-perf]")), None)
        if line is None:
            return {"available": False}
        if "perf_unavailable=1" in line:
            return {"available": False, "raw": line}
        values: dict[str, str] = {}
        for key, value in re.findall(r"([A-Za-z_]+)=([^\s]+)", line):
            values[key] = value

        def number(name: str, *, integer: bool = False):
            raw = values.get(name)
            if raw is None:
                return None
            try:
                return int(raw) if integer else float(raw)
            except ValueError:
                return None

        return {
            "available": True,
            "prefill_time_ms": number("prefill_ms"),
            "prefill_tokens": number("prefill_tokens", integer=True),
            "prefill_tokens_per_second": number("prefill_tps"),
            "generate_time_ms": number("decode_ms"),
            "generate_tokens": number("decode_tokens", integer=True),
            "generate_tokens_per_second": number("decode_tps"),
            "peak_memory_usage_mb": number("memory_mb"),
            "kv_before": number("kv_before", integer=True),
            "kv_after": number("kv_after", integer=True),
            "raw": line,
        }

    @staticmethod
    def _parse_result_line(line: str) -> tuple[str, str, float, str]:
        parts = line.rstrip("\r\n").split("\t", 4)
        if len(parts) != 5 or parts[0] != RESULT_MARKER:
            raise ValueError(f"无法解析RKLLM结果行: {line!r}")
        request_id, status, wall_ms, encoded = parts[1], parts[2], float(parts[3]), parts[4]
        try:
            answer = base64.b64decode(encoded.encode("ascii"), validate=True).decode("utf-8")
        except Exception as exc:
            raise ValueError("RKLLM结果Base64/UTF-8无效") from exc
        return request_id, status, wall_ms, answer

    def _complete(self, operation: str, content: str, request_id: str) -> tuple[str, dict[str, Any]]:
        if operation not in {"START", "TOOL"}:
            raise ValueError(operation)
        if self.process.stdin is None:
            raise RuntimeError("stdin未建立")
        safe_id = self._safe_request_id(request_id)
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        started = time.perf_counter()
        sampler = (
            BoardMetricsSampler(self.process.pid, self.metrics_sample_interval_ms)
            if self.collect_board_metrics
            else None
        )
        if sampler is not None:
            sampler.start()
        sampled_metrics: dict[str, Any] | None = None

        def stop_sampler() -> dict[str, Any] | None:
            nonlocal sampled_metrics
            if sampler is not None and sampled_metrics is None:
                sampled_metrics = sampler.stop()
            return sampled_metrics

        try:
            self.process.stdin.write(f"{operation}\t{safe_id}\t{encoded}\n")
            self.process.stdin.flush()
        except Exception:
            stop_sampler()
            raise
        logs: list[str] = []

        def build_telemetry(inference_ms: float | None, partial_output: str = "") -> dict[str, Any]:
            telemetry = {
                "operation": operation,
                "runtime_status": "ok" if inference_ms is not None else "runtime_error",
                "inference_ms": inference_ms,
                "wall_latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "runtime_log": list(logs),
                "rkllm_perf": self._parse_perf(logs),
                "board_metrics": stop_sampler(),
            }
            if partial_output:
                telemetry["first_raw_output"] = partial_output
            return telemetry

        request_deadline = time.monotonic() + self.request_timeout
        while True:
            try:
                remaining = request_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("等待RKLLM完整响应超时")
                line = self._readline(remaining)
            except Exception as exc:
                raise RKLLMRuntimeError(str(exc), build_telemetry(None)) from exc
            if PROTOCOL_ERROR_MARKER in line:
                message = line.rstrip("\r\n")
                raise RKLLMRuntimeError(message, build_telemetry(None))
            if not line.startswith(RESULT_MARKER + "\t"):
                logs.append(line.rstrip("\r\n"))
                continue
            returned_id, status, inference_ms, answer = self._parse_result_line(line)
            if returned_id != safe_id:
                logs.append(line.rstrip("\r\n"))
                continue
            telemetry = build_telemetry(inference_ms, answer if status != "ok" else "")
            telemetry["runtime_status"] = status
            if status != "ok":
                log_tail = "\n".join(logs[-80:])
                detail = (
                    f"RKLLM运行失败: status={status}, "
                    f"inference_ms={inference_ms:.3f}, partial_output={answer!r}"
                )
                if log_tail:
                    detail += f"\n--- runtime log ---\n{log_tail}"
                raise RKLLMRuntimeError(detail, telemetry)
            return answer, telemetry

    def start_case(self, content: str, request_id: str) -> tuple[str, dict[str, Any]]:
        return self._complete("START", content, request_id)

    def continue_tool(self, content: str, request_id: str) -> tuple[str, dict[str, Any]]:
        return self._complete("TOOL", content, request_id)

    def reset(self, request_id: str = "manual") -> None:
        if self.process.stdin is None:
            raise RuntimeError("stdin未建立")
        safe_id = self._safe_request_id(request_id)
        self.process.stdin.write(f"RESET\t{safe_id}\n")
        self.process.stdin.flush()
        while True:
            line = self._readline(self.request_timeout)
            if line.startswith(RESET_MARKER + "\t"):
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) == 3 and parts[1] == safe_id and parts[2] == "ok":
                    return
                raise RuntimeError(line.rstrip("\r\n"))

    def _delete_prompt_file(self) -> None:
        try:
            self._system_prompt_path.unlink(missing_ok=True)
        except Exception:
            pass

    def close(self) -> None:
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None and process.stdin is not None:
            try:
                process.stdin.write("QUIT\n")
                process.stdin.flush()
                process.wait(timeout=10)
            except Exception:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        reader = getattr(self, "_stdout_reader", None)
        if reader is not None:
            reader.join(timeout=2)
        if process is not None:
            for stream in (process.stdin, process.stdout):
                if stream is not None and not stream.closed:
                    stream.close()
        self._delete_prompt_file()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
