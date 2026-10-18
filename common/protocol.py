from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .task_families import interface_slug, normalize_task_family


@dataclass(frozen=True)
class ProtocolProfile:
    name: str
    schema_transport: str
    repair_limit: int

    @property
    def structured_output(self) -> bool:
        return self.schema_transport != "none"


PROFILES = {
    "P0_prompt_only": ProtocolProfile("P0_prompt_only", "none", 0),
    "P2_prompt_schema_repair1": ProtocolProfile(
        "P2_prompt_schema_repair1", "prompt", 1
    ),
}


def get_profile(name: str) -> ProtocolProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"unsupported_protocol_profile:{name}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def object_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def schema_sha256(schema: dict[str, Any]) -> str:
    return object_sha256(schema)


def prompt_schema_instruction(schema: dict[str, Any]) -> str:
    """Exact portable counterpart of the structured RKLLM prompt suffix."""
    return (
        " [强制结构输出] 不要复述输入，不要Markdown，不要解释。"
        "只填写下列JSON Schema允许的字段，并只输出一个JSON值。JSON_SCHEMA="
        + canonical_json(schema)
        + " [助手]"
    )


def protocol_schema_path(protocol_root: Path, interface: str, task_family: Any) -> Path:
    """Resolve a schema in the released package layout."""
    family = normalize_task_family(task_family)
    public_interface = interface_slug(interface)
    candidates = [
        protocol_root / "protocols" / f"{family}.json",
        protocol_root / public_interface / "protocols" / f"{family}.json",
        # Compatibility with older checkouts; released files use the public
        # interface directories above.
        protocol_root / "protocols" / public_interface / "protocols" / f"{family}.json",
        protocol_root / f"dr_tc{('DGC','MSC','AIR','FAR','DCR','PMU','REQ').index(family)+1}.json" if public_interface == "State-Given" else protocol_root / f"eia_tc{('DGC','MSC','AIR','FAR','DCR','PMU','REQ').index(family)+1}.json",
    ]
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise FileNotFoundError(
        f"protocol schema not found for {public_interface}/{family}; tried: "
        + ", ".join(str(path) for path in candidates)
    )


def load_protocol_schema(protocol_root: Path, interface: str, task_family: Any) -> dict[str, Any]:
    value = json.loads(
        protocol_schema_path(protocol_root, interface, task_family).read_text(encoding="utf-8")
    )
    if not isinstance(value, dict):
        raise ValueError("protocol_schema_must_be_object")
    return value


def strict_json_object(text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error:{exc.msg}"
    if not isinstance(value, dict):
        return None, "json_root_not_object"
    return value, None


def recover_json_value(text: str) -> tuple[Any | None, str | None]:
    try:
        return json.loads(text.strip()), None
    except json.JSONDecodeError as exc:
        strict_error = f"json_decode_error:{exc.msg}"
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list)):
            return value, None
    return None, strict_error or "json_value_not_found"


def recover_json_object(text: str) -> tuple[dict[str, Any] | None, str | None]:
    value, error = recover_json_value(text)
    if isinstance(value, dict):
        return value, None
    if value is not None:
        return None, "json_root_not_object"
    return None, error


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def schema_errors(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate the JSON-Schema subset used by EdgeHome protocol files.

    This intentionally does not silently depend on jsonschema on the RK3588 board.
    """
    if "oneOf" in schema:
        alternatives = [schema_errors(value, item, path) for item in schema["oneOf"]]
        matched = sum(not errors for errors in alternatives)
        return [] if matched == 1 else [f"{path}:oneOf_matched_{matched}"]
    if "anyOf" in schema:
        alternatives = [schema_errors(value, item, path) for item in schema["anyOf"]]
        return [] if any(not errors for errors in alternatives) else [f"{path}:anyOf_no_match"]
    if "const" in schema and value != schema["const"]:
        return [f"{path}:const_mismatch"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}:enum_mismatch"]
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_matches_type(value, item) for item in expected):
            return [f"{path}:type_mismatch"]
    elif isinstance(expected, str) and not _matches_type(value, expected):
        return [f"{path}:expected_{expected}"]
    errors: list[str] = []
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}:required")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}:additional_property")
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                errors.extend(schema_errors(child, child_schema, f"{path}.{key}"))
    if isinstance(value, str) and isinstance(schema.get("minLength"), int):
        if len(value) < schema["minLength"]:
            errors.append(f"{path}:minLength")
    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            errors.append(f"{path}:minItems")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            errors.append(f"{path}:maxItems")
        if isinstance(schema.get("items"), dict):
            for index, child in enumerate(value):
                errors.extend(schema_errors(child, schema["items"], f"{path}[{index}]"))
    return errors


def _schema_mode_with_field(schema: dict[str, Any], field: str) -> str | None:
    choices = schema.get("oneOf") if isinstance(schema.get("oneOf"), list) else [schema]
    for item in choices:
        if not isinstance(item, dict):
            continue
        properties = item.get("properties")
        if not isinstance(properties, dict) or field not in properties:
            continue
        mode_schema = properties.get("mode")
        if isinstance(mode_schema, dict) and isinstance(mode_schema.get("const"), str):
            return mode_schema["const"]
    return None


def coerce_protocol_shape(
    schema: dict[str, Any], parsed: Any
) -> tuple[dict[str, Any] | None, str]:
    """Formatting-only normalization mirrored from rkllm_structured_persistent.cpp."""
    notes: list[str] = []
    if isinstance(parsed, list):
        mode = _schema_mode_with_field(schema, "actions")
        if mode is None:
            return None, "unsupported_root_shape"
        return {"mode": mode, "actions": parsed}, "wrapped_actions_array"
    if not isinstance(parsed, dict):
        return None, "unsupported_root_shape"

    candidate = json.loads(json.dumps(parsed, ensure_ascii=False))
    if "tool_call_" in candidate and "tool_call" not in candidate:
        candidate["tool_call"] = candidate.pop("tool_call_")
        notes.append("renamed_tool_call_key")
    elif (
        isinstance(candidate.get("name"), str)
        and isinstance(candidate.get("arguments"), dict)
        and "tool_call" not in candidate
    ):
        candidate = {"tool_call": candidate}
        notes.append("wrapped_tool_call")
    elif isinstance(candidate.get("actions"), list) and "mode" not in candidate:
        mode = _schema_mode_with_field(schema, "actions")
        if mode is not None:
            candidate["mode"] = mode
            notes.append("added_mode")

    if "tool_call" in candidate or "final_output" in candidate:
        for key in (
            "type",
            "required",
            "properties",
            "additionalProperties",
            "oneOf",
            "anyOf",
            "$schema",
        ):
            if key in candidate:
                candidate.pop(key)
                notes.append("removed_schema_metadata")

    actions = candidate.get("actions")
    if isinstance(actions, list):
        for action in actions:
            if not isinstance(action, dict) or not isinstance(action.get("arguments"), dict):
                continue
            arguments = action["arguments"]
            if "device_id" not in action and "device_id" in arguments:
                action["device_id"] = arguments.pop("device_id")
                notes.append("lifted_device_id")
            if "service" not in action and "service" in arguments:
                action["service"] = arguments.pop("service")
                notes.append("lifted_service")
            if isinstance(arguments.get("arguments"), dict):
                nested = arguments.pop("arguments")
                nested.update(arguments)
                action["arguments"] = nested
                notes.append("flattened_arguments")
    return candidate, "+".join(notes)


def analyze_output(text: str, schema: dict[str, Any]) -> dict[str, Any]:
    strict_value, strict_error = strict_json_object(text)
    recovered, recovery_error = recover_json_value(text)
    raw_errors = [] if strict_value is None else schema_errors(strict_value, schema)
    normalized, normalization_note = coerce_protocol_shape(schema, recovered)
    errors = [] if normalized is None else schema_errors(normalized, schema)
    protocol_valid = normalized is not None and not errors
    return {
        "strict_json_valid": strict_value is not None,
        "recoverable_json_valid": isinstance(recovered, dict),
        "recovered_json_value_valid": recovered is not None,
        "raw_schema_valid": strict_value is not None and not raw_errors,
        "schema_valid": protocol_valid,
        "strict_error": strict_error,
        "recovery_error": recovery_error,
        "schema_errors": errors,
        "raw_schema_errors": raw_errors,
        "normalization_used": protocol_valid
        and (strict_value is None or bool(normalization_note)),
        "normalization_note": normalization_note,
        "parsed": normalized if protocol_valid else recovered,
    }


def normalize_eia_decision(decision: dict[str, Any]) -> dict[str, Any]:
    has_tool = (
        isinstance(decision.get("tool_call"), dict)
        or decision.get("type") == "tool_call"
        or (
            isinstance(decision.get("name") or decision.get("tool_name"), str)
            and isinstance(decision.get("arguments"), dict)
        )
    )
    has_final = (
        isinstance(decision.get("final_output"), dict)
        or isinstance(decision.get("final"), dict)
        or decision.get("type") == "final"
        or "mode" in decision
        or (decision.get("final_turn") is True and isinstance(decision.get("output"), dict))
    )
    if has_tool and has_final:
        raise ValueError("multiple_decisions_in_turn")
    nested = decision.get("tool_call")
    if isinstance(nested, dict):
        return {
            "kind": "tool_call",
            "name": nested.get("name") or nested.get("tool_name"),
            "arguments": nested.get("arguments"),
            "format_normalized": "tool_name" in nested and "name" not in nested,
        }
    if decision.get("type") == "tool_call":
        return {
            "kind": "tool_call",
            "name": decision.get("name"),
            "arguments": decision.get("arguments"),
            "format_normalized": True,
        }
    if isinstance(decision.get("name") or decision.get("tool_name"), str):
        return {
            "kind": "tool_call",
            "name": decision.get("name") or decision.get("tool_name"),
            "arguments": decision.get("arguments"),
            "format_normalized": True,
        }
    if isinstance(decision.get("final_output"), dict):
        return {"kind": "final", "output": decision["final_output"], "format_normalized": False}
    if isinstance(decision.get("final"), dict):
        return {"kind": "final", "output": decision["final"], "format_normalized": True}
    if decision.get("type") == "final" and isinstance(decision.get("output"), dict):
        return {"kind": "final", "output": decision["output"], "format_normalized": True}
    if "mode" in decision:
        return {"kind": "final", "output": decision, "format_normalized": True}
    if decision.get("final_turn") is True and isinstance(decision.get("output"), dict):
        return {"kind": "final", "output": decision["output"], "format_normalized": True}
    raise ValueError("decision_must_be_tool_call_or_final")


def generic_repair_instruction(raw: str = "", error: str = "") -> str:
    bounded_raw = raw[:2000]
    return (
        " [格式纠正] 上一次输出未执行，因为不符合规定的Structured Output。错误="
        + (error or "invalid_json_or_output_schema")
        + "。上一次输出="
        + bounded_raw
        + "。请重新回答；只能输出一个符合output_protocol的JSON对象，"
        "不要解释，不要Markdown。 [助手]"
    )


def tool_feedback(name: str, result: dict[str, Any]) -> str:
    return canonical_json(
        {
            "tool_result": {"name": name, "result": result},
            "instruction": "根据此真实结果继续；仍然只输出下一次tool_call或final_output二者之一。",
        }
    )


def call_fingerprint(name: str, arguments: dict[str, Any]) -> str:
    return canonical_json({"name": name, "arguments": arguments})
