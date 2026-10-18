from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .rkllm_model_client import PersistentRKLLMClient as PromptClient
from .rkllm_model_client import TokenCounter
from .structured_rkllm_model_client import PersistentRKLLMClient as StructuredClient


class SchemaAwareTokenCounter:
    def __init__(self, base: TokenCounter, schema: dict[str, Any]):
        self.base = base
        schema_text = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        self.schema_tokens = base.count(schema_text) + 64
        self.method = f"{base.method}+structured_schema_estimate"

    def count_messages(self, messages: list[dict[str, str]]) -> int:
        return self.base.count_messages(messages) + self.schema_tokens


class PromptRKLLMBackend:
    backend_name = "rkllm_prompt_persistent"
    schema_enforced = False
    schema_transport = "none"

    def __init__(
        self,
        *,
        binary: str,
        model: str,
        max_new_tokens: int,
        max_context_len: int,
        ld_library_path: str,
        system_prompt: str,
        startup_timeout: float,
        request_timeout: float,
        collect_board_metrics: bool = True,
        metrics_sample_interval_ms: int = 100,
    ):
        self.client = PromptClient(
            binary,
            model,
            max_new_tokens,
            max_context_len,
            ld_library_path,
            system_prompt,
            startup_timeout,
            request_timeout,
            collect_board_metrics,
            metrics_sample_interval_ms,
        )

    def start_case(self, content: str, request_id: str):
        return self.client.start_case(content, request_id)

    def continue_user(self, content: str, request_id: str):
        return self.client.continue_tool(content, request_id)

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class StructuredRKLLMBackend:
    backend_name = "rkllm_structured_persistent"
    schema_enforced = True
    schema_transport = "prompt"

    def __init__(
        self,
        *,
        binary: str,
        model: str,
        max_new_tokens: int,
        max_context_len: int,
        ld_library_path: str,
        system_prompt: str,
        schema_path: Path,
        startup_timeout: float,
        request_timeout: float,
        collect_board_metrics: bool = True,
        metrics_sample_interval_ms: int = 100,
    ):
        self.system_prompt = system_prompt
        self.messages: list[dict[str, str]] = []
        self.client = StructuredClient(
            binary,
            model,
            max_new_tokens,
            max_context_len,
            ld_library_path,
            startup_timeout,
            request_timeout,
            str(schema_path),
            collect_board_metrics,
            metrics_sample_interval_ms,
        )

    def _complete(self, request_id: str):
        prompt = self.client.render_messages(self.messages)
        raw, telemetry = self.client.complete_prompt(prompt, request_id)
        self.messages.append({"role": "assistant", "content": raw})
        return raw, telemetry

    def start_case(self, content: str, request_id: str):
        self.messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": content},
        ]
        return self._complete(request_id)

    def continue_user(self, content: str, request_id: str):
        self.messages.append({"role": "user", "content": content})
        return self._complete(request_id)

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
