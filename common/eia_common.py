from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable

from common.tc7_contract import merge_system_instruction, result_contracts


TC_IDS = tuple(range(1, 8))


def default_suite_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{number} 不是JSON对象")
                rows.append(value)
    return rows


def write_plain_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    if os.name != "nt":
        path.write_bytes(data); return
    script = ("$payload=[Console]::In.ReadToEnd();"
              "$target=[Environment]::GetEnvironmentVariable('EIA_PLAIN_WRITE_PATH');"
              "[System.IO.File]::WriteAllBytes($target,[Convert]::FromBase64String($payload))")
    env = os.environ.copy(); env["EIA_PLAIN_WRITE_PATH"] = str(path.resolve())
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                               input=base64.b64encode(data), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               check=False, env=env)
    if completed.returncode != 0:
        raise OSError(completed.stderr.decode("utf-8", errors="replace"))
    if path.read_bytes()[:11].startswith(b"%TSD-Header"):
        raise OSError(f"透明加密仍然存在: {path}")


def write_json(path: Path, value: Any) -> None:
    write_plain_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    write_plain_text(path, "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def _source_tool(source_tools: Any, name: str) -> dict[str, Any] | None:
    if not isinstance(source_tools, list):
        return None
    matches = [tool for tool in source_tools if isinstance(tool, dict) and tool.get("name") == name]
    if len(matches) > 1:
        raise ValueError(f"duplicate_source_tool:{name}")
    return copy.deepcopy(matches[0]) if matches else None


def _tc4_create_automation_fallback() -> dict[str, Any]:
    nullable_text = {"type": ["string", "null"]}
    return {
        "name": "create_automation",
        "description": (
            "注册未来自动化规则，不立即控制设备。conditions.time_cron 使用七位 Quartz Cron，"
            "字段顺序为秒、分、时、日、月、星期、年，秒字段为 0。conditions.state_expr 是"
            "device('设备ID').state.字段 操作符 值形式的字符串。未使用的条件写 null，"
            "time_cron 与 state_expr 不得同时为 null。"
        ),
        "parameters": object_schema(
            {
                "automation_id": {"type": "string", "minLength": 1},
                "name": {"type": "string", "minLength": 1},
                "conditions": object_schema(
                    {"time_cron": nullable_text, "state_expr": nullable_text},
                    ["time_cron", "state_expr"],
                ),
                "actions": {
                    "type": "array",
                    "minItems": 1,
                    "items": object_schema(
                        {"device_id": {"type": "string"}, "service": {"type": "string"}, "arguments": {"type": "object"}},
                        ["device_id", "service", "arguments"],
                    ),
                },
            },
            ["conditions", "actions"],
        ),
    }


def tool_definitions(tc: int, source_tools: Any = None) -> list[dict[str, Any]]:
    text = lambda: {"type": "string"}
    tools = [
        {"name": "get_home_overview", "description": "取得当前家庭的高层统计，不返回设备状态。", "parameters": object_schema({})},
        {"name": "list_rooms", "description": "列出当前家庭的房间ID和名称。", "parameters": object_schema({})},
        {"name": "get_room_state", "description": "查询一个房间的占用、温湿度等房间级状态。", "parameters": object_schema({"room_id": text()}, ["room_id"])},
        {"name": "list_devices", "description": "按可选房间、设备类型或型号筛选设备；只返回定位元数据，不返回当前state。", "parameters": object_schema({"room_id": text(), "device_type": text(), "spec_id": text()})},
        {"name": "get_device_state", "description": "查询一台设备的完整当前状态和定位信息。", "parameters": object_schema({"device_id": text()}, ["device_id"])},
        {"name": "get_device_spec", "description": "查询一台设备所属型号的属性、服务、参数和前置条件。", "parameters": object_schema({"device_id": text()}, ["device_id"])},
    ]
    if tc in {1, 2, 3, 5, 6}:
        tools.append({"name": "control_device", "description": "调用说明书中支持的服务控制设备；控制前应先查询同一设备说明书。", "parameters": object_schema({"device_id": text(), "service": text(), "arguments": {"type": "object"}}, ["device_id", "service", "arguments"])})
    if tc == 4:
        # TC4's source dataset owns the task-specific DSL contract.  Copy it
        # verbatim instead of replacing it with a lossy generic object schema.
        tools.append(_source_tool(source_tools, "create_automation") or _tc4_create_automation_fallback())
    return tools


def output_protocol(tc: int) -> dict[str, Any]:
    shared = {
        "instruction": "每轮只能二选一：需要工具时只输出tool_call_example；任务结束时只输出final_output_example。两者不得同时出现。",
        "tool_call_example": {"tool_call": {"name": "工具名", "arguments": {}}},
        "one_decision_per_turn": True,
        "no_batch_tool_calls": True,
    }
    if tc == 3:
        shared["final_output_example"] = {"final_output": {"mode": "completed 或 clarification", "response": "仅澄清时填写"}}
    elif tc == 7:
        shared["final_output_example"] = {
            "final_output": {"mode": "answer", "result": "必须且只能选择result_contracts中的一种结构"}
        }
        shared["result_contracts"] = result_contracts()
    else:
        shared["final_output_example"] = {"final_output": {"mode": "completed"}}
    return shared


def system_instruction(tc: int) -> str:
    base = (
        "你正在参加智能家居EIA（Environment-Interactive Agent）评测。详细房间状态、设备清单、设备状态和说明书没有直接提供，"
        "必须根据需要调用环境工具查询。每轮只能输出output_protocol规定的一个JSON对象；工具调用和最终输出二选一，工具结果返回后才能决定下一步。"
        "不得猜测未查询的信息，不得读取或索要Gold、题型标签或其他用例。"
    )
    if tc == 3:
        return base + "若经过必要查询仍无法唯一、合理地确定用户意图，可以结束为一次有针对性的澄清问题；否则执行后结束。"
    if tc == 4:
        return base + "只允许注册未来自动化，不允许即时控制。"
    if tc == 7:
        return base + "本题严格只读，只能查询并返回结构化答案。"
    return base + "完成控制后结束；不得把计划中的动作当成已经执行。"


def build_payload(case: dict[str, Any], tc: int) -> dict[str, Any]:
    source = case.get("model_input")
    if not isinstance(source, dict) or not isinstance(source.get("home"), dict):
        raise ValueError(f"{case.get('id')}: model_input/home缺失")
    payload = copy.deepcopy(source)
    home = payload.pop("home")
    source_tools = payload.pop("tools", None)
    payload["system_instruction"] = (
        merge_system_instruction(system_instruction(tc), source.get("system_instruction"))
        if tc == 7
        else system_instruction(tc)
    )
    payload["home_metadata"] = {
        "home_id": home.get("home_id", case["id"] + "_home"),
        "home_type": case.get("home_type", home.get("home_type", "unknown")),
    }
    payload["tools"] = tool_definitions(tc, source_tools)
    payload["output_protocol"] = output_protocol(tc)
    return payload


def source_case_path(suite_root: Path, tc: int) -> Path:
    return suite_root / f"tc{tc}" / "data" / f"tc{tc}_zh.jsonl"
