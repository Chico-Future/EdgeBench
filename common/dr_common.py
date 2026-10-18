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
    rows: list[dict[str, Any]] = []
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
              "$target=[Environment]::GetEnvironmentVariable('DR_PLAIN_WRITE_PATH');"
              "[System.IO.File]::WriteAllBytes($target,[Convert]::FromBase64String($payload))")
    env = os.environ.copy(); env["DR_PLAIN_WRITE_PATH"] = str(path.resolve())
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


def relevant_specs(home: dict[str, Any], specs: dict[str, Any]) -> dict[str, Any]:
    ids = sorted({device["spec_id"] for device in home.get("devices", [])})
    missing = [spec_id for spec_id in ids if spec_id not in specs]
    if missing:
        raise ValueError(f"说明书缺失: {missing}")
    return {spec_id: copy.deepcopy(specs[spec_id]) for spec_id in ids}


def output_protocol(tc: int) -> dict[str, Any]:
    action = {"device_id": "string", "service": "string", "arguments": "object"}
    if tc in {1, 2, 5, 6}:
        return {
            "allowed_modes": ["execution"],
            "schema": {"mode": "execution", "actions": [action]},
            "rules": ["只输出一个JSON对象", "actions按实际执行顺序排列", "不得输出工具调用或自行伪造状态"],
        }
    if tc == 3:
        return {
            "allowed_modes": ["execution", "clarification"],
            "execution_schema": {"mode": "execution", "actions": [action]},
            "clarification_schema": {"mode": "clarification", "response": "自然、针对当前歧义的追问"},
            "rules": ["完整上下文已能唯一确定时直接执行", "信息仍不足时只提出必要追问", "只输出一个JSON对象"],
        }
    if tc == 4:
        conditions = {
            "time_cron": "string|null（七位 Quartz Cron：秒 分 时 日 月 星期 年；秒字段为0）",
            "state_expr": "string|null（device('设备ID').state.字段 运算符 值）",
        }
        return {
            "allowed_modes": ["automation"],
            "schema": {
                "mode": "automation",
                "automations": [{"conditions": conditions, "actions": [action]}],
            },
            "rules": [
                "只注册未来规则，不立即控制设备",
                "conditions只能且必须包含time_cron和state_expr；未使用的条件写null，二者不得同时为null",
                "state_expr示例：device('dev_123').state.humidity_percent >= 75",
                "多个独立时间分别输出规则",
                "只输出一个JSON对象",
            ],
        }
    return {
        "allowed_modes": ["answer"],
        "schema": {"mode": "answer", "result": "必须且只能选择result_contracts中的一种结构"},
        "result_contracts": result_contracts(),
        "rules": ["只读，不修改设备", "不得输出response、actions、automations或工具调用", "只输出一个JSON对象"],
    }


def system_instruction(tc: int) -> str:
    base = (
        "你正在参加智能家居DR（Direct Reasoning）评测。完整家庭状态和本家庭涉及的设备说明书已经一次性提供。"
        "不得调用工具；请直接依据当前输入完成任务。不得读取或猜测Gold、题型标签或其他用例。严格按照output_protocol只输出一个JSON对象。"
    )
    if tc == 3:
        return base + "若当前信息可以唯一、合理且可执行地确定动作则执行，否则提出一次有针对性的澄清问题。"
    if tc == 4:
        return base + (
            "本题只创建未来自动化规则，不执行即时控制。自动化conditions必须严格使用"
            "time_cron和state_expr两个字段，未使用的字段写null。"
        )
    if tc == 7:
        return base + "本题只查询当前环境，任何设备控制或自动化注册都不允许。"
    return base + "输出完成用户当前请求所需的有序设备动作。"


def build_payload(case: dict[str, Any], specs_doc: dict[str, Any], tc: int) -> dict[str, Any]:
    source = case.get("model_input")
    if not isinstance(source, dict) or not isinstance(source.get("home"), dict):
        raise ValueError(f"{case.get('id')}: model_input/home缺失")
    payload = copy.deepcopy(source)
    payload.pop("tools", None)
    payload["system_instruction"] = (
        merge_system_instruction(system_instruction(tc), source.get("system_instruction"))
        if tc == 7
        else system_instruction(tc)
    )
    specs = specs_doc.get("specs")
    if not isinstance(specs, dict):
        raise ValueError("device_specs.json缺少specs对象")
    payload["device_specs"] = relevant_specs(payload["home"], specs)
    payload["output_protocol"] = output_protocol(tc)
    return payload


def source_paths(suite_root: Path, tc: int) -> tuple[Path, Path]:
    tc_root = suite_root / f"tc{tc}"
    return tc_root / "data" / f"tc{tc}_zh.jsonl", tc_root / "data" / "device_specs.json"
