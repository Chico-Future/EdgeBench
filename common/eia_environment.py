from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

from .eia_common import read_json, read_jsonl
from .task_families import TASK_FAMILIES, normalize_task_family, task_family_index


def _load_module(path: Path, unique_name: str):
    code_dir = str(path.parent)
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)
    spec = importlib.util.spec_from_file_location(unique_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    return module


def _state_delta(before: Any, after: Any, prefix: str = "") -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in before or key not in after:
                changes.append({"path": path, "before": before.get(key), "after": after.get(key)})
            else:
                changes.extend(_state_delta(before[key], after[key], path))
    elif before != after:
        changes.append({"path": prefix, "before": before, "after": after})
    return changes


class EIAEnvironment:
    """Gold-free environment used by the participant-facing State-Seeking runner."""

    def __init__(self, suite_root: Path, task_family: str, case_id: str):
        self.task_family = normalize_task_family(task_family)
        self.suite_root, self.tc, self.case_id = suite_root.resolve(), task_family_index(self.task_family), case_id
        self._init_released_layout()

    def _init_released_layout(self) -> None:
        roots = [self.suite_root]
        language = self._case_language()
        if language is not None:
            roots.insert(0, self.suite_root / language)
        family_root = next(
            root for root in roots if (root / self.task_family / "data" / "cases.jsonl").is_file()
        )
        family_data = family_root / self.task_family / "data"
        cases = {row["id"]: row for row in read_jsonl(family_data / "cases.jsonl")}
        if self.case_id not in cases:
            raise KeyError(f"unknown case: {self.case_id}")
        self.case = cases[self.case_id]
        self.home = copy.deepcopy(self.case["model_input"]["home"])
        self.initial_home = copy.deepcopy(self.home)
        self.specs = read_json(family_data / "device_specs.json")["specs"]
        self.queried_specs: set[str] = set()
        self.automations: list[dict[str, Any]] = []
        self.trace: list[dict[str, Any]] = []
        self._action_module = None
        self._automation_runtime = None

    def _case_language(self) -> str:
        for language in ("en", "zh"):
            if f"_{language}_" in self.case_id:
                return language
        raise ValueError(f"case_id_missing_language:{self.case_id}")

    def _room(self, room_id: str) -> dict[str, Any]:
        for room in self.home.get("rooms", []):
            if room.get("room_id") == room_id: return room
        raise ValueError("unknown_room")

    def _device(self, device_id: str) -> dict[str, Any]:
        for device in self.home.get("devices", []):
            if device.get("device_id") == device_id: return device
        raise ValueError("unknown_device")

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        event = {"tool_name": name, "arguments": copy.deepcopy(arguments)}
        try:
            if not isinstance(arguments, dict): raise ValueError("arguments_must_be_object")
            if name == "get_home_overview":
                if arguments: raise ValueError("unexpected_arguments")
                result = {"ok": True, "home_id": self.home.get("home_id", self.case_id + "_home"),
                          "home_type": self.case.get("home_type", self.home.get("home_type")),
                          "room_count": len(self.home.get("rooms", [])), "device_count": len(self.home.get("devices", []))}
            elif name == "list_rooms":
                if arguments: raise ValueError("unexpected_arguments")
                result = {"ok": True, "rooms": [
                    {
                        "room_id": room.get("room_id"),
                        "room_name": room.get("room_name", room.get("name")),
                    }
                    for room in self.home.get("rooms", [])
                ]}
            elif name == "get_room_state":
                if set(arguments) != {"room_id"}: raise ValueError("invalid_arguments")
                room = self._room(arguments["room_id"])
                result = {"ok": True, "room": copy.deepcopy(room)}
            elif name == "list_devices":
                if not set(arguments) <= {"room_id", "device_type", "spec_id"}: raise ValueError("invalid_arguments")
                devices = self.home.get("devices", [])
                for key in ("room_id", "device_type", "spec_id"):
                    if key in arguments: devices = [device for device in devices if device.get(key) == arguments[key]]
                fields = ("device_id", "spec_id", "device_type", "alias", "room_id", "room_name", "placement", "tags")
                result = {"ok": True, "devices": [{key: copy.deepcopy(device[key]) for key in fields if key in device} for device in devices]}
            elif name == "get_device_state":
                if set(arguments) != {"device_id"}: raise ValueError("invalid_arguments")
                result = {"ok": True, "device": copy.deepcopy(self._device(arguments["device_id"]))}
            elif name == "get_device_spec":
                if set(arguments) != {"device_id"}: raise ValueError("invalid_arguments")
                device = self._device(arguments["device_id"]); self.queried_specs.add(device["device_id"])
                result = {"ok": True, "device_id": device["device_id"], "spec_id": device["spec_id"], "spec": copy.deepcopy(self.specs[device["spec_id"]])}
            elif name == "control_device":
                result = self._control(arguments)
            elif name == "create_automation":
                result = self._create_automation(arguments)
            else:
                raise ValueError("unknown_tool")
        except (AssertionError, KeyError, TypeError, ValueError) as exc:
            result = {"ok": False, "error": str(exc)}
        event["result"] = copy.deepcopy(result); self.trace.append(event)
        return result

    def _control(self, action: dict[str, Any]) -> dict[str, Any]:
        if self.tc in {4, 7}: raise ValueError("control_forbidden_for_this_tc")
        if set(action) != {"device_id", "service", "arguments"} or not isinstance(action.get("arguments"), dict):
            raise ValueError("invalid_control_arguments")
        if action["device_id"] not in self.queried_specs: raise ValueError("control_before_spec_lookup")
        self._device(action["device_id"])
        before = copy.deepcopy(self.home); candidate = copy.deepcopy(self.home)
        changes = self._apply_released_action(candidate, copy.deepcopy(action))
        self.home = candidate
        return {"ok": True, "state_changes": copy.deepcopy(changes)}

    @staticmethod
    def _get_path(value: dict[str, Any], path: str) -> Any:
        current: Any = value
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise ValueError(f"missing_state_path:{path}")
            current = current[part]
        return current

    @staticmethod
    def _set_path(value: dict[str, Any], path: str, new_value: Any) -> None:
        parts = path.split(".")
        current = value
        for part in parts[:-1]:
            child = current.get(part)
            if not isinstance(child, dict):
                raise ValueError(f"missing_state_path:{path}")
            current = child
        current[parts[-1]] = copy.deepcopy(new_value)

    def _apply_released_action(
        self, home: dict[str, Any], action: dict[str, Any]
    ) -> list[dict[str, Any]]:
        device = next(
            (item for item in home.get("devices", []) if item.get("device_id") == action["device_id"]),
            None,
        )
        if device is None:
            raise ValueError("unknown_device")
        spec = self.specs.get(device.get("spec_id"), {})
        service = (spec.get("services") or {}).get(action["service"])
        if not isinstance(service, dict):
            raise ValueError("unsupported_service")
        arguments = action["arguments"]
        declared_arguments = service.get("arguments") or {}
        if set(arguments) != set(declared_arguments):
            raise ValueError("invalid_service_arguments")

        state = device.get("state")
        if not isinstance(state, dict):
            raise ValueError("device_state_missing")
        minimum_preconditions = service.get("minimum_preconditions") or {}
        for condition_key, expected in {
            **(service.get("preconditions") or {}),
            **minimum_preconditions,
        }.items():
            actual = self._get_path(state, condition_key)
            if condition_key in minimum_preconditions:
                if not isinstance(actual, (int, float)) or actual < expected:
                    raise ValueError("service_precondition_failed")
            elif actual != expected:
                raise ValueError("service_precondition_failed")

        before = copy.deepcopy(home)
        for path, effect in (service.get("effects") or {}).items():
            if isinstance(effect, str) and effect.startswith("$"):
                argument_name = effect[1:]
                if argument_name not in arguments:
                    raise ValueError("effect_argument_missing")
                value = arguments[argument_name]
            else:
                value = effect
            self._set_path(state, path, value)
        return _state_delta(before, home)

    def _create_automation(self, rule: dict[str, Any]) -> dict[str, Any]:
        if self.task_family != "FAR": raise ValueError("automation_not_available_for_this_task_family")
        if not isinstance(rule.get("conditions"), dict) or not isinstance(rule.get("actions"), list):
            raise ValueError("invalid_automation_rule")
        conditions = rule["conditions"]
        if set(conditions) != {"time_cron", "state_expr"}:
            raise ValueError("invalid_automation_conditions")
        if conditions["time_cron"] is None and conditions["state_expr"] is None:
            raise ValueError("empty_automation_conditions")
        canonical = copy.deepcopy(rule)
        self.automations.append(copy.deepcopy(canonical))
        return {"ok": True, "registered": True, "automation_index": len(self.automations) - 1}

    def snapshot(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "tc": self.tc, "tool_trace": copy.deepcopy(self.trace),
                "final_home": copy.deepcopy(self.home), "automations": copy.deepcopy(self.automations)}
