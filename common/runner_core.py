from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .eia_common import write_jsonl
from .eia_environment import EIAEnvironment
from .task_families import (
    normalize_task_family,
    task_family_for_rows,
    task_family_index,
)
from .protocol import (
    ProtocolProfile,
    analyze_output,
    call_fingerprint,
    generic_repair_instruction,
    normalize_eia_decision,
    object_sha256,
    schema_sha256,
    tool_feedback,
)


class CompletionBackend(Protocol):
    backend_name: str
    schema_enforced: bool
    schema_transport: str

    def start_case(self, content: str, request_id: str) -> tuple[str, dict[str, Any]]: ...

    def continue_user(self, content: str, request_id: str) -> tuple[str, dict[str, Any]]: ...


class MessageTokenCounter(Protocol):
    method: str

    def count_messages(self, messages: list[dict[str, str]]) -> int: ...


@dataclass(frozen=True)
class RunConfig:
    interface: str
    profile: ProtocolProfile
    max_new_tokens: int
    max_context_len: int
    max_steps: int = 20


def system_prompt_for_rows(rows: list[dict[str, Any]]) -> str:
    prompts = {row["model_input"]["system_instruction"] for row in rows}
    if len(prompts) != 1:
        raise ValueError("one_run_requires_one_system_instruction")
    return next(iter(prompts))


def task_family_for_row(row: dict[str, Any]) -> str:
    return normalize_task_family(row.get("task_family"))


def user_content(row: dict[str, Any]) -> str:
    payload = row["model_input"]
    return json.dumps(
        {key: value for key, value in payload.items() if key != "system_instruction"},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def protocol_metadata(
    backend: CompletionBackend,
    config: RunConfig,
    schema: dict[str, Any],
) -> dict[str, Any]:
    schema_transport = getattr(
        backend, "schema_transport", "backend" if backend.schema_enforced else "none"
    )
    return {
        "profile": config.profile.name,
        "backend": backend.backend_name,
        "schema_enforced": backend.schema_enforced,
        "schema_transport": schema_transport,
        "schema_sha256": schema_sha256(schema),
        "repair_limit": config.profile.repair_limit,
        "max_context_len": config.max_context_len,
        "max_new_tokens": config.max_new_tokens,
        "max_steps": config.max_steps if config.interface == "State-Seeking" else None,
    }


def _budget(
    counter: MessageTokenCounter,
    messages: list[dict[str, str]],
    config: RunConfig,
) -> dict[str, Any]:
    prompt_tokens = counter.count_messages(messages)
    return {
        "count_method": counter.method,
        "prompt_tokens": prompt_tokens,
        "reserved_output_tokens": config.max_new_tokens,
        "max_context_len": config.max_context_len,
        "within_limit": prompt_tokens + config.max_new_tokens <= config.max_context_len,
    }


def _attempt_record(
    raw: str,
    telemetry: dict[str, Any],
    schema: dict[str, Any],
    budget: dict[str, Any],
    *,
    transport: str,
    counts_toward_runtime: bool = True,
) -> dict[str, Any]:
    analysis = analyze_output(raw, schema)
    return {
        "transport": transport,
        "counts_toward_runtime": counts_toward_runtime,
        "raw_output": raw,
        "strict_json_valid": analysis["strict_json_valid"],
        "recoverable_json_valid": analysis["recoverable_json_valid"],
        "schema_valid": analysis["schema_valid"],
        "raw_schema_valid": analysis["raw_schema_valid"],
        "strict_error": analysis["strict_error"],
        "recovery_error": analysis["recovery_error"],
        "schema_errors": analysis["schema_errors"],
        "raw_schema_errors": analysis["raw_schema_errors"],
        "normalization_used": analysis["normalization_used"],
        "normalization_note": analysis["normalization_note"],
        "context_budget": budget,
        "telemetry": telemetry,
        "parsed": analysis["parsed"],
    }


def generate_protocol_turn(
    backend: CompletionBackend,
    counter: MessageTokenCounter,
    config: RunConfig,
    schema: dict[str, Any],
    messages: list[dict[str, str]],
    first_call: Callable[[], tuple[str, dict[str, Any]]],
    continuation_call: Callable[[str, str], tuple[str, dict[str, Any]]],
    request_id: str,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    external_repairs = 0
    pending_call: Callable[[], tuple[str, dict[str, Any]]] = first_call
    accepted_raw: str | None = None
    accepted_parsed: dict[str, Any] | None = None
    error: str | None = None

    while True:
        budget = _budget(counter, messages, config)
        if not budget["within_limit"]:
            error = "context_limit_skipped"
            break
        try:
            raw, telemetry = pending_call()
        except Exception as exc:
            telemetry = getattr(exc, "telemetry", {})
            raw = str(telemetry.get("first_raw_output", ""))
            if raw or telemetry:
                attempts.append(
                    _attempt_record(
                        raw, telemetry, schema, budget, transport="backend_rejected"
                    )
                )
            error = f"{type(exc).__name__}: {exc}"
            break

        first_raw = str(telemetry.get("first_raw_output", raw) or raw)
        internal_repair = bool(telemetry.get("structured_retry_used"))
        attempts.append(_attempt_record(first_raw, telemetry, schema, budget, transport="first_generation"))
        accepted_analysis = analyze_output(raw, schema)
        if internal_repair:
            attempts.append(
                _attempt_record(
                    raw,
                    telemetry,
                    schema,
                    budget,
                    transport="backend_internal_repair",
                    counts_toward_runtime=False,
                )
            )

        accepted_for_profile = (
            accepted_analysis["recoverable_json_valid"]
            if config.profile.name == "P0_prompt_only"
            else accepted_analysis["schema_valid"]
        )
        if accepted_for_profile:
            accepted_raw = raw
            accepted_parsed = accepted_analysis["parsed"]
            messages.append({"role": "assistant", "content": raw})
            break

        messages.append({"role": "assistant", "content": raw})
        if external_repairs >= config.profile.repair_limit:
            error = "output_protocol_rejected"
            break
        repair_error = ";".join(accepted_analysis["schema_errors"][:8])
        if not repair_error:
            repair_error = str(
                accepted_analysis.get("recovery_error")
                or accepted_analysis.get("strict_error")
                or "invalid_json_or_output_schema"
            )
        repair = generic_repair_instruction(raw, repair_error)
        messages.append({"role": "user", "content": repair})
        external_repairs += 1
        repair_id = f"{request_id}__repair{external_repairs}"
        pending_call = lambda content=repair, rid=repair_id: continuation_call(content, rid)

    internal_repairs = sum(
        1 for attempt in attempts if attempt["transport"] == "backend_internal_repair"
    )
    repair_attempts = internal_repairs + external_repairs
    profile_violations: list[str] = []
    backend_transport = getattr(
        backend, "schema_transport", "backend" if backend.schema_enforced else "none"
    )
    if backend_transport != config.profile.schema_transport:
        profile_violations.append("schema_transport_mismatch")
    if repair_attempts > config.profile.repair_limit:
        profile_violations.append("repair_limit_exceeded")
    first = attempts[0] if attempts else {}
    accepted = analyze_output(accepted_raw, schema) if accepted_raw is not None else {}
    return {
        "raw_output": first.get("raw_output", ""),
        "accepted_output": accepted_raw,
        "parsed": accepted_parsed,
        "attempts": attempts,
        "error": error,
        "format_diagnostics": {
            "first_strict_json_valid": first.get("strict_json_valid", False),
            "first_recoverable_json_valid": first.get("recoverable_json_valid", False),
            "first_schema_valid": first.get("raw_schema_valid", False),
            "accepted_strict_json_valid": accepted.get("strict_json_valid", False),
            "accepted_schema_valid": accepted.get("schema_valid", False),
            "normalization_used": any(
                bool(item.get("normalization_used")) for item in attempts
            ),
            "normalization_notes": [
                item["normalization_note"]
                for item in attempts
                if item.get("normalization_note")
            ],
            "repair_used": repair_attempts > 0,
            "repair_attempts": repair_attempts,
            "external_repair_attempts": external_repairs,
            "backend_internal_repair_attempts": internal_repairs,
            "profile_violations": profile_violations,
        },
    }


def _aggregate_generation_telemetry(turns: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = [attempt for turn in turns for attempt in turn.get("attempts", [])]
    telemetry_rows = [
        attempt.get("telemetry", {})
        for attempt in attempts
        if attempt.get("counts_toward_runtime", True)
    ]
    usage_keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    usage = {
        key: sum(int((row.get("usage") or {}).get(key) or 0) for row in telemetry_rows)
        for key in usage_keys
    }
    return {
        "generation_attempts": len(attempts),
        "repair_attempts": sum(
            int(turn.get("format_diagnostics", {}).get("repair_attempts", 0) or 0)
            for turn in turns
        ),
        "total_inference_ms": round(
            sum(float(row.get("inference_ms", 0) or 0) for row in telemetry_rows), 3
        ),
        "total_wall_latency_ms": round(
            sum(float(row.get("wall_latency_ms", 0) or 0) for row in telemetry_rows), 3
        ),
        "provider_usage": usage,
    }


def run_dr(
    rows: list[dict[str, Any]],
    output: Path,
    backend: CompletionBackend,
    counter: MessageTokenCounter,
    config: RunConfig,
    schema: dict[str, Any],
) -> list[dict[str, Any]]:
    system_prompt = system_prompt_for_rows(rows)
    protocol = protocol_metadata(backend, config, schema)
    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        content = user_content(row)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ]
        turn = generate_protocol_turn(
            backend,
            counter,
            config,
            schema,
            messages,
            lambda c=content, rid=row["id"]: backend.start_case(c, rid),
            backend.continue_user,
            row["id"],
        )
        telemetry = _aggregate_generation_telemetry([turn])
        telemetry["model_turns"] = telemetry["generation_attempts"]
        result = {
            "id": row["id"],
            "task_family": task_family_for_row(row),
            "input_record_sha256": object_sha256(row),
            "prediction": turn["parsed"],
            "raw_output": turn["raw_output"],
            "accepted_output": turn["accepted_output"],
            "attempts": turn["attempts"],
            "format_diagnostics": turn["format_diagnostics"],
            "error": turn["error"],
            "context_budget": turn["attempts"][0]["context_budget"] if turn["attempts"] else None,
            "telemetry": telemetry,
            "protocol": protocol,
        }
        results.append(result)
        write_jsonl(output, results)
        print(f"[{index:03d}/{len(rows):03d}] {'OK' if result['error'] is None else result['error']} {row['id']}", flush=True)
    return results


def run_eia(
    rows: list[dict[str, Any]],
    output: Path,
    suite_root: Path,
    backend: CompletionBackend,
    counter: MessageTokenCounter,
    config: RunConfig,
    schema: dict[str, Any],
) -> list[dict[str, Any]]:
    system_prompt = system_prompt_for_rows(rows)
    protocol = protocol_metadata(backend, config, schema)
    completed: list[dict[str, Any]] = []
    for case_index, row in enumerate(rows, 1):
        task_family = task_family_for_row(row)
        tc = task_family_index(task_family)
        env = EIAEnvironment(suite_root, task_family, row["id"])
        content = user_content(row)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ]
        turns: list[dict[str, Any]] = []
        final: dict[str, Any] | None = None
        error: str | None = None
        pending_content: str | None = None
        seen_calls: dict[tuple[int, str], int] = {}
        mutation_epoch = 0
        duplicate_tool_calls = 0
        protocol_violations = 0

        for step in range(config.max_steps):
            request_id = f"{row['id']}__step{step + 1}"
            if step == 0:
                first_call = lambda c=content, rid=request_id: backend.start_case(c, rid)
            else:
                if pending_content is None:
                    error = "missing_pending_tool_content"
                    break
                first_call = lambda c=pending_content, rid=request_id: backend.continue_user(c, rid)
            turn = generate_protocol_turn(
                backend,
                counter,
                config,
                schema,
                messages,
                first_call,
                backend.continue_user,
                request_id,
            )
            turn["step"] = step
            turn["decision"] = turn["parsed"]
            turn["normalized_decision"] = None
            turns.append(turn)
            if turn["error"] is not None:
                error = turn["error"]
                break
            try:
                normalized = normalize_eia_decision(turn["parsed"] or {})
                turn["normalized_decision"] = normalized
            except ValueError as exc:
                error = str(exc)
                protocol_violations += 1
                break
            if normalized["kind"] == "final":
                final = normalized.get("output")
                break
            name, arguments = normalized.get("name"), normalized.get("arguments")
            if not isinstance(name, str) or not isinstance(arguments, dict):
                error = "invalid_tool_turn"
                protocol_violations += 1
                break
            fingerprint = call_fingerprint(name, arguments)
            seen_key = (mutation_epoch, fingerprint)
            if seen_key in seen_calls:
                duplicate_tool_calls += 1
                turn["duplicate_tool_call"] = True
            seen_calls[seen_key] = seen_calls.get(seen_key, 0) + 1
            result = env.call(name, arguments)
            if name in {"control_device", "create_automation"} and result.get("ok"):
                mutation_epoch += 1
            pending_content = tool_feedback(name, result)
            messages.append({"role": "user", "content": pending_content})
            print(
                f"[{case_index:03d}/{len(rows):03d} step {step + 1:02d}/{config.max_steps:02d}] "
                f"TOOL {name} ok={bool(result.get('ok'))} {row['id']}",
                flush=True,
            )

        if final is None and error is None:
            error = "max_steps_exceeded"
        snap = env.snapshot()
        telemetry = _aggregate_generation_telemetry(turns)
        telemetry.update(
            {
                "model_turns": telemetry["generation_attempts"],
                "decision_turns": len(turns),
                "duplicate_tool_calls": duplicate_tool_calls,
                "protocol_violations": protocol_violations,
                "tool_calls": len(snap["tool_trace"]),
                "failed_tool_calls": sum(
                    not bool(item.get("result", {}).get("ok")) for item in snap["tool_trace"]
                ),
            }
        )
        record = {
            "id": row["id"],
            "task_family": task_family,
            "input_record_sha256": object_sha256(row),
            "final_output": final,
            "tool_trace": snap["tool_trace"],
            "automations": snap["automations"],
            "initial_home_sha256": object_sha256(env.initial_home),
            "final_home_sha256": object_sha256(snap["final_home"]),
            "turns": turns,
            "error": error,
            "telemetry": telemetry,
            "protocol": protocol,
        }
        completed.append(record)
        write_jsonl(output, completed)
        print(f"[{case_index:03d}/{len(rows):03d}] {'OK' if error is None else error} {row['id']}", flush=True)
    return completed
