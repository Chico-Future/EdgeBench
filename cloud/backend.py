from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from common.protocol import prompt_schema_instruction


class CloudTokenCounter:
    def __init__(
        self,
        tokenizer_json: str | None,
        *,
        safety_factor: float = 1.25,
        schema: dict[str, Any] | None = None,
    ):
        self.safety_factor = safety_factor
        self.tokenizer = None
        self.schema_tokens = 0
        self.method = "heuristic_portable_chat"
        if tokenizer_json:
            try:
                from tokenizers import Tokenizer
            except ImportError as exc:
                raise RuntimeError("--tokenizer-json requires the tokenizers package") from exc
            self.tokenizer = Tokenizer.from_file(tokenizer_json)
            self.method = "tokenizer_json_portable_chat"
        if schema is not None:
            self.schema_tokens = self.count_text(
                json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
            ) + 64
            self.method += "+structured_schema_estimate"

    @property
    def exact(self) -> bool:
        return self.tokenizer is not None

    def count_text(self, text: str) -> int:
        if self.tokenizer is not None:
            return len(self.tokenizer.encode(text, add_special_tokens=False).ids)
        cjk = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
        ascii_like = len(text) - cjk
        return max(1, math.ceil((cjk * 1.15 + ascii_like / 3.0) * self.safety_factor))

    def count_messages(self, messages: list[dict[str, str]]) -> int:
        rendered = "".join(
            f"<|message|>{item['role']}\n{item['content']}<|end|>\n" for item in messages
        ) + "<|message|>assistant\n"
        return self.count_text(rendered) + self.schema_tokens


class OpenAICompatibleBackend:
    backend_name = "openai_compatible_chat_completions"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str,
        system_prompt: str,
        max_new_tokens: int,
        temperature: float | None,
        timeout: float,
        schema: dict[str, Any] | None,
        schema_transport: str | None = None,
        max_tokens_field: str = "max_tokens",
        seed: int | None = None,
        request_extra: dict[str, Any] | None = None,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key_env = api_key_env
        self.system_prompt = system_prompt
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.schema = schema
        self.schema_transport = schema_transport or ("prompt" if schema is not None else "none")
        if self.schema_transport not in {"none", "prompt"}:
            raise ValueError(f"unsupported_schema_transport:{self.schema_transport}")
        if (self.schema_transport == "none") != (schema is None):
            raise ValueError("schema_transport_schema_mismatch")
        self.schema_enforced = self.schema_transport != "none"
        self.backend_name = f"openai_compatible_chat_completions:{self.schema_transport}"
        self.max_tokens_field = max_tokens_field
        self.seed = seed
        self.request_extra = dict(request_extra or {})
        reserved = {
            "model",
            "messages",
            "temperature",
            "max_tokens",
            "max_completion_tokens",
            "response_format",
            "seed",
        }
        collisions = reserved.intersection(self.request_extra)
        if collisions:
            raise ValueError(f"request_extra_reserved_keys:{','.join(sorted(collisions))}")
        self.messages: list[dict[str, str]] = []

    def _content(self, message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            )
        if message.get("refusal"):
            raise RuntimeError(f"provider_refusal:{message['refusal']}")
        raise ValueError("provider_message_content_missing")

    def _complete(self, request_id: str) -> tuple[str, dict[str, Any]]:
        request_messages = [dict(item) for item in self.messages]
        if self.schema_transport == "prompt":
            if not request_messages or request_messages[-1].get("role") != "user":
                raise RuntimeError("prompt_schema_requires_trailing_user_message")
            request_messages[-1]["content"] = (
                str(request_messages[-1].get("content", ""))
                + prompt_schema_instruction(self.schema or {})
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": request_messages,
            self.max_tokens_field: self.max_new_tokens,
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.seed is not None:
            payload["seed"] = self.seed
        payload.update(self.request_extra)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "X-Client-Request-Id": request_id}
        api_key = os.environ.get(self.api_key_env, "") if self.api_key_env else ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(self.url, data=encoded, headers=headers, method="POST")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            raise RuntimeError(f"http_error:{exc.code}:{detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"transport_error:{exc.reason}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        value = json.loads(body)
        choices = value.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("provider_choices_missing")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("provider_message_missing")
        raw = self._content(message)
        self.messages.append({"role": "assistant", "content": raw})
        usage = value.get("usage") if isinstance(value.get("usage"), dict) else {}
        telemetry = {
            "operation": "chat.completions",
            "runtime_status": "ok",
            "http_status": status,
            "inference_ms": latency_ms,
            "wall_latency_ms": latency_ms,
            "provider_response_id": value.get("id"),
            "provider_model": value.get("model"),
            "system_fingerprint": value.get("system_fingerprint"),
            "finish_reason": choices[0].get("finish_reason"),
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
            "request_sha256": hashlib.sha256(encoded).hexdigest(),
            "schema_transport": self.schema_transport,
        }
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
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
