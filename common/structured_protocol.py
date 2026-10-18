from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from common.tc7_contract import result_json_schema


def obj(properties: dict[str, Any], required: list[str] | None = None, *, extra: bool = False) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": extra,
    }


STRING = {"type": "string", "minLength": 1}
EMPTY = obj({})
ACTION = obj(
    {
        "device_id": STRING,
        "service": STRING,
        "arguments": {"type": "object"},
    },
    ["device_id", "service", "arguments"],
)
ACTIONS = {"type": "array", "items": ACTION, "minItems": 1}
TC4_CONDITIONS = obj(
    {
        "time_cron": {"type": ["string", "null"]},
        "state_expr": {"type": ["string", "null"]},
    },
    ["time_cron", "state_expr"],
)


def exact_mode(mode: str, extra_properties: dict[str, Any], extra_required: list[str]) -> dict[str, Any]:
    return obj({"mode": {"const": mode}, **extra_properties}, ["mode", *extra_required])


def dr_schema(tc: int) -> dict[str, Any]:
    if tc in {1, 2, 5, 6}:
        return exact_mode("execution", {"actions": ACTIONS}, ["actions"])
    if tc == 3:
        return {
            "oneOf": [
                exact_mode("execution", {"actions": ACTIONS}, ["actions"]),
                exact_mode("clarification", {"response": STRING}, ["response"]),
            ]
        }
    if tc == 4:
        automation = obj(
            {
                "conditions": TC4_CONDITIONS,
                "actions": ACTIONS,
                "automation_id": STRING,
                "name": STRING,
            },
            ["conditions", "actions"],
        )
        return exact_mode(
            "automation",
            {"automations": {"type": "array", "items": automation, "minItems": 1}},
            ["automations"],
        )
    if tc == 7:
        return exact_mode("answer", {"result": result_json_schema()}, ["result"])
    raise ValueError(f"unsupported_tc:{tc}")


def tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return obj(
        {"tool_call": obj({"name": {"const": name}, "arguments": arguments}, ["name", "arguments"])},
        ["tool_call"],
    )


QUERY_TOOLS = [
    tool("get_home_overview", EMPTY),
    tool("list_rooms", EMPTY),
    tool("get_room_state", obj({"room_id": STRING}, ["room_id"])),
    tool("list_devices", obj({"room_id": STRING, "device_type": STRING, "spec_id": STRING})),
    tool("get_device_state", obj({"device_id": STRING}, ["device_id"])),
    tool("get_device_spec", obj({"device_id": STRING}, ["device_id"])),
]


def final(output: dict[str, Any]) -> dict[str, Any]:
    return obj({"final_output": output}, ["final_output"])


def eia_schema(tc: int) -> dict[str, Any]:
    if tc not in range(1, 8):
        raise ValueError(f"unsupported_tc:{tc}")
    alternatives = list(QUERY_TOOLS)
    if tc in {1, 2, 3, 5, 6}:
        alternatives.append(tool("control_device", ACTION))
    if tc == 4:
        alternatives.append(
            tool(
                "create_automation",
                obj(
                    {
                        "conditions": TC4_CONDITIONS,
                        "actions": ACTIONS,
                        "automation_id": STRING,
                        "name": STRING,
                    },
                    ["conditions", "actions"],
                ),
            )
        )
    if tc == 3:
        alternatives.extend(
            [
                final(exact_mode("completed", {}, [])),
                final(exact_mode("clarification", {"response": STRING}, ["response"])),
            ]
        )
    elif tc == 7:
        alternatives.append(final(exact_mode("answer", {"result": result_json_schema()}, ["result"])))
    else:
        alternatives.append(final(exact_mode("completed", {}, [])))
    return {"oneOf": alternatives}


def materialize_schema(mode: str, tc: int) -> Path:
    schema = dr_schema(tc) if mode == "dr" else eia_schema(tc) if mode == "eia" else None
    if schema is None:
        raise ValueError(f"unsupported_mode:{mode}")
    directory = Path(tempfile.gettempdir()) / "edgehome_rkllm_protocols"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{mode}_tc{tc}.schema"
    path.write_text(json.dumps(schema, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path.resolve()
