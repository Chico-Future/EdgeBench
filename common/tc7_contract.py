from __future__ import annotations

import copy
from typing import Any


TC7_RESULT_CONTRACTS: dict[str, dict[str, Any]] = {
    "count": {"answer_type": "count", "value": "integer"},
    "device_list": {"answer_type": "device_list", "device_ids": ["device_id"]},
    "status": {
        "answer_type": "status",
        "items": [{"device_id": "string", "facts": "object keyed only by requested attributes"}],
    },
    "locations": {
        "answer_type": "locations",
        "items": [{"device_id": "string", "room_name": "string", "placement": "string"}],
    },
    "comparison": {
        "answer_type": "comparison",
        "metric": "string",
        "values": [{"device_id": "string", "value": "value"}],
        "relation": "first_greater|second_greater|equal",
        "winner_device_ids": ["device_id"],
    },
    "extremum": {
        "answer_type": "extremum",
        "metric": "string",
        "direction": "max|min",
        "value": "value",
        "device_ids": ["device_id"],
    },
}

TC7_TASK_CONTRACT = (
    "只回答用户当前提出的查询，不得控制、修改或假设改变任何设备状态。"
    "设备开关、配置值、房间环境和设备位置均以本轮可见输入或工具查询结果为准；"
    "关闭设备保留的配置不等于正在产生效果。"
    "问题中的灯或照明设备只指A型灯、B型灯、彩色落地灯和风扇灯的照明部分，不包含晾衣架辅助灯；"
    "风扇只指独立智能风扇和风扇灯的风扇部分，不包含晾衣架风干模块、空调或净化器。"
    "需要判断设备能力时，可按device_id查询设备说明书；说明书查询不得改变家庭状态。"
    "回答必须只包含mode='answer'和结构化result，不要生成response字段。"
    "数量题的result使用answer_type=count和value；设备列表题使用answer_type=device_list和device_ids；"
    "状态题使用answer_type=status及包含device_id、facts的items；facts键使用用户问题中的中文属性名，"
    "状态枚举值直接复制环境中的原始值（如on/off、raised/lowered），不得自行翻译或改写；"
    "位置题使用answer_type=locations及包含device_id、room_name、placement的items；"
    "比较题使用answer_type=comparison、metric、values、relation、winner_device_ids；"
    "values按问题中的设备顺序排列，每项只含device_id和value；"
    "relation只能是first_greater、second_greater或equal；"
    "极值题使用answer_type=extremum、metric、direction、value、device_ids。"
    "灯光亮度指标metric使用brightness_percent；窗帘或百叶帘开合指标使用opening_percent；"
    "机器人电量指标使用battery_percent。设备列表必须使用device_id；"
    "没有符合条件的设备时返回空列表或数量0，不要编造。"
)


def result_contracts() -> dict[str, dict[str, Any]]:
    """Return the participant-visible TC7 answer contracts without any gold values."""
    return copy.deepcopy(TC7_RESULT_CONTRACTS)


def merge_system_instruction(generic_instruction: str, source_instruction: Any) -> str:
    """Preserve TC7 semantics without importing DR-only state-delivery wording into EIA."""
    if not isinstance(source_instruction, str) or not source_instruction.strip():
        raise ValueError("tc7_source_system_instruction_missing")
    required_anchors = (
        "answer_type=count",
        "answer_type=device_list",
        "answer_type=status",
        "answer_type=locations",
        "answer_type=comparison",
        "answer_type=extremum",
    )
    missing = [anchor for anchor in required_anchors if anchor not in source_instruction]
    if missing:
        raise ValueError(f"tc7_source_contract_incomplete:{missing}")
    return generic_instruction + "\n\nTC7任务专用契约（必须同时遵守）：\n" + TC7_TASK_CONTRACT


def _obj(properties: dict[str, Any], required: list[str], *, extra: bool = False) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": extra,
    }


_TEXT = {"type": "string", "minLength": 1}
_DEVICE_IDS = {"type": "array", "items": _TEXT}
_ANY_VALUE: dict[str, Any] = {}


def result_json_schema() -> dict[str, Any]:
    """Exact structural union used by both DR and EIA protocol validation."""
    count = _obj(
        {"answer_type": {"const": "count"}, "value": {"type": "integer"}},
        ["answer_type", "value"],
    )
    device_list = _obj(
        {"answer_type": {"const": "device_list"}, "device_ids": _DEVICE_IDS},
        ["answer_type", "device_ids"],
    )
    status_item = _obj(
        {
            "device_id": _TEXT,
            "facts": {"type": "object", "additionalProperties": True},
        },
        ["device_id", "facts"],
    )
    status = _obj(
        {
            "answer_type": {"const": "status"},
            "items": {"type": "array", "items": status_item},
        },
        ["answer_type", "items"],
    )
    location_item = _obj(
        {"device_id": _TEXT, "room_name": _TEXT, "placement": _TEXT},
        ["device_id", "room_name", "placement"],
    )
    locations = _obj(
        {
            "answer_type": {"const": "locations"},
            "items": {"type": "array", "items": location_item},
        },
        ["answer_type", "items"],
    )
    comparison_value = _obj(
        {"device_id": _TEXT, "value": _ANY_VALUE},
        ["device_id", "value"],
    )
    comparison = _obj(
        {
            "answer_type": {"const": "comparison"},
            "metric": _TEXT,
            "values": {"type": "array", "items": comparison_value},
            "relation": {"enum": ["first_greater", "second_greater", "equal"]},
            "winner_device_ids": _DEVICE_IDS,
        },
        ["answer_type", "metric", "values", "relation", "winner_device_ids"],
    )
    extremum = _obj(
        {
            "answer_type": {"const": "extremum"},
            "metric": _TEXT,
            "direction": {"enum": ["max", "min"]},
            "value": _ANY_VALUE,
            "device_ids": _DEVICE_IDS,
        },
        ["answer_type", "metric", "direction", "value", "device_ids"],
    )
    return {"oneOf": [count, device_list, status, locations, comparison, extremum]}
