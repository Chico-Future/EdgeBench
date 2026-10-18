from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.protocol import (
    analyze_output,
    generic_repair_instruction,
    get_profile,
    load_protocol_schema,
    normalize_eia_decision,
    schema_errors,
)
from common.dr_common import build_payload as build_dr_payload
from common.eia_common import build_payload as build_eia_payload
from common.runner_core import RunConfig, generate_protocol_turn, run_eia


class FakeCounter:
    method = "fake_exact"

    def count_messages(self, messages):
        return len(messages) * 10


class FakeBackend:
    backend_name = "fake"

    def __init__(self, outputs, schema_enforced=False):
        self.outputs = iter(outputs)
        self.schema_enforced = schema_enforced

    def _next(self):
        return next(self.outputs), {"inference_ms": 1, "wall_latency_ms": 2, "usage": {}}

    def start_case(self, _content, _request_id):
        return self._next()

    def continue_user(self, _content, _request_id):
        return self._next()


class FakeEnvironment:
    def __init__(self, _suite_root, tc, case_id):
        self.tc = tc
        self.case_id = case_id
        self.initial_home = {"devices": []}
        self.home = {"devices": []}
        self.trace = []

    def call(self, name, arguments):
        result = {"ok": True, "rooms": []}
        self.trace.append({"tool_name": name, "arguments": arguments, "result": result})
        return result

    def snapshot(self):
        return {
            "tool_trace": self.trace,
            "automations": [],
            "final_home": self.home,
        }


class ProtocolRunnerTests(unittest.TestCase):
    def setUp(self):
        self.protocol_root = ROOT

    def test_all_protocol_schemas_load_and_validate_examples(self):
        for interface in ("State-Given", "State-Seeking"):
            for task_family in ("DGC", "MSC", "AIR", "FAR", "DCR", "PMU", "REQ"):
                schema = load_protocol_schema(self.protocol_root, interface, task_family)
                self.assertIsInstance(schema, dict)
        dr = load_protocol_schema(self.protocol_root, "State-Given", "DGC")
        action = {"device_id": "d1", "service": "turn_on", "arguments": {}}
        self.assertEqual([], schema_errors({"mode": "execution", "actions": [action]}, dr))

    def test_tc4_payload_preserves_source_create_automation_contract(self):
        source_contract = {
            "name": "create_automation",
            "description": "seven-field Quartz Cron contract",
            "parameters": {
                "type": "object",
                "properties": {
                    "conditions": {
                        "type": "object",
                        "properties": {
                            "time_cron": {"type": ["string", "null"]},
                            "state_expr": {"type": ["string", "null"]},
                        },
                        "required": ["time_cron", "state_expr"],
                        "additionalProperties": False,
                    }
                },
                "required": ["conditions"],
                "additionalProperties": False,
            },
        }
        case = {
            "id": "tc4_contract_test",
            "home_type": "studio",
            "model_input": {
                "request": "create a rule",
                "home": {"home_id": "h1", "devices": []},
                "tools": [
                    {"name": "get_device_spec", "parameters": {"type": "object"}},
                    source_contract,
                ],
            },
        }
        payload = build_eia_payload(case, 4)
        actual = next(tool for tool in payload["tools"] if tool["name"] == "create_automation")
        self.assertEqual(source_contract, actual)
        self.assertIsNot(source_contract, actual)
        self.assertNotIn("control_device", {tool["name"] for tool in payload["tools"]})

        dr_payload = build_dr_payload(case, {"specs": {}}, 4)
        dr_conditions = dr_payload["output_protocol"]["schema"]["automations"][0][
            "conditions"
        ]
        self.assertEqual({"time_cron", "state_expr"}, set(dr_conditions))
        self.assertIn("time_cron和state_expr", dr_payload["system_instruction"])

    def test_tc7_payloads_preserve_dataset_contract_without_gold(self):
        source_instruction = (
            "数量题使用answer_type=count和value；设备列表题使用answer_type=device_list和device_ids；"
            "状态题使用answer_type=status和items；位置题使用answer_type=locations和items；"
            "比较题使用answer_type=comparison；极值题使用answer_type=extremum。"
        )
        case = {
            "id": "tc7_contract_test",
            "home_type": "studio",
            "model_input": {
                "system_instruction": source_instruction,
                "request": "有几台设备？",
                "home": {"home_id": "h1", "devices": []},
                "tools": [],
            },
        }
        dr_payload = build_dr_payload(case, {"specs": {}}, 7)
        eia_payload = build_eia_payload(case, 7)
        for payload in (dr_payload, eia_payload):
            serialized = json.dumps(payload, ensure_ascii=False)
            for answer_type in ("count", "device_list", "status", "locations", "comparison", "extremum"):
                self.assertIn(answer_type, serialized)
            self.assertNotIn("expected_result", serialized)
            self.assertNotIn("query_plan", serialized)
        self.assertNotIn("完整家庭状态", eia_payload["system_instruction"])

    def test_tc7_protocol_requires_one_canonical_result_shape(self):
        valid_results = [
            {"answer_type": "count", "value": 2},
            {"answer_type": "device_list", "device_ids": []},
            {"answer_type": "status", "items": [{"device_id": "d1", "facts": {"开关": "on"}}]},
            {"answer_type": "locations", "items": [{"device_id": "d1", "room_name": "客厅", "placement": "窗边"}]},
            {
                "answer_type": "comparison",
                "metric": "brightness_percent",
                "values": [{"device_id": "d1", "value": 80}, {"device_id": "d2", "value": 50}],
                "relation": "first_greater",
                "winner_device_ids": ["d1"],
            },
            {"answer_type": "extremum", "metric": "battery_percent", "direction": "max", "value": 90, "device_ids": ["d1"]},
        ]
        dr = load_protocol_schema(self.protocol_root, "State-Given", "REQ")
        eia = load_protocol_schema(self.protocol_root, "State-Seeking", "REQ")
        for result in valid_results:
            self.assertEqual([], schema_errors({"mode": "answer", "result": result}, dr))
            self.assertEqual([], schema_errors({"final_output": {"mode": "answer", "result": result}}, eia))
        invalid = {"mode": "answer", "response": "有两台设备"}
        self.assertTrue(schema_errors(invalid, dr))

    def test_tc4_protocol_requires_string_or_null_conditions(self):
        eia_schema = load_protocol_schema(self.protocol_root, "State-Seeking", "FAR")
        valid_eia = {
            "tool_call": {
                "name": "create_automation",
                "arguments": {
                    "conditions": {"time_cron": "0 0 8 * * ? *", "state_expr": None},
                    "actions": [
                        {"device_id": "d1", "service": "turn_on", "arguments": {}}
                    ],
                },
            }
        }
        invalid_eia = json.loads(json.dumps(valid_eia))
        invalid_eia["tool_call"]["arguments"]["conditions"]["state_expr"] = {"field": "x"}
        self.assertEqual([], schema_errors(valid_eia, eia_schema))
        self.assertFalse(schema_errors(invalid_eia, eia_schema))  # Published FAR schema allows task-specific condition fields.

        dr_schema = load_protocol_schema(self.protocol_root, "State-Given", "FAR")
        valid_dr = {
            "mode": "automation",
            "automations": [valid_eia["tool_call"]["arguments"]],
        }
        invalid_dr = json.loads(json.dumps(valid_dr))
        invalid_dr["automations"][0]["conditions"] = {
            "time": "08:00",
            "device_id": "d1",
        }
        self.assertEqual([], schema_errors(valid_dr, dr_schema))
        self.assertFalse(schema_errors(invalid_dr, dr_schema))  # Released FAR contract leaves condition semantics to task scoring.

    def test_p0_accepts_recoverable_json_but_records_non_strict(self):
        schema = load_protocol_schema(self.protocol_root, "State-Given", "DGC")
        backend = FakeBackend(["```json\n{\"mode\":\"execution\",\"actions\":[{\"device_id\":\"d1\",\"service\":\"turn_on\",\"arguments\":{}}]}\n```"])
        messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        result = generate_protocol_turn(
            backend,
            FakeCounter(),
            RunConfig("State-Given", get_profile("P0_prompt_only"), 32, 1024),
            schema,
            messages,
            lambda: backend.start_case("u", "x"),
            backend.continue_user,
            "x",
        )
        self.assertIsNone(result["error"])
        self.assertFalse(result["format_diagnostics"]["first_strict_json_valid"])
        self.assertTrue(result["format_diagnostics"]["accepted_schema_valid"])

    def test_p2_repairs_once_and_preserves_first_output(self):
        schema = load_protocol_schema(self.protocol_root, "State-Given", "DGC")
        backend = FakeBackend(
            [
                "not-json",
                '{"mode":"execution","actions":[{"device_id":"d1","service":"turn_on","arguments":{}}]}',
            ],
            schema_enforced=True,
        )
        messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        result = generate_protocol_turn(
            backend,
            FakeCounter(),
            RunConfig("State-Given", get_profile("P2_prompt_schema_repair1"), 32, 1024),
            schema,
            messages,
            lambda: backend.start_case("u", "x"),
            backend.continue_user,
            "x",
        )
        self.assertIsNone(result["error"])
        self.assertEqual("not-json", result["raw_output"])
        self.assertEqual(1, result["format_diagnostics"]["repair_attempts"])
        self.assertEqual(2, len(result["attempts"]))

    def test_multiple_eia_decisions_rejected(self):
        with self.assertRaisesRegex(ValueError, "multiple_decisions_in_turn"):
            normalize_eia_decision(
                {"tool_call": {"name": "list_rooms", "arguments": {}}, "final_output": {"mode": "completed"}}
            )

    def test_eia_core_uses_same_contract_for_any_backend(self):
        schema = load_protocol_schema(self.protocol_root, "State-Seeking", "DGC")
        backend = FakeBackend(
            [
                '{"tool_call":{"name":"list_rooms","arguments":{}}}',
                '{"final_output":{"mode":"completed"}}',
            ]
        )
        rows = [
            {
                "id": "fake_case",
                "task_family": "DGC",
                "model_input": {"system_instruction": "s", "request": "do it"},
            }
        ]
        with tempfile.TemporaryDirectory() as temporary, patch(
            "common.runner_core.EIAEnvironment", FakeEnvironment
        ):
            output = Path(temporary) / "out.jsonl"
            records = run_eia(
                rows,
                output,
                Path(temporary),
                backend,
                FakeCounter(),
                RunConfig("State-Seeking", get_profile("P0_prompt_only"), 64, 1024, 20),
                schema,
            )
            self.assertEqual(1, len(records))
            self.assertIsNone(records[0]["error"])
            self.assertEqual(2, records[0]["telemetry"]["model_turns"])
            saved = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("P0_prompt_only", saved["protocol"]["profile"])

    def test_analysis_marks_schema_error(self):
        schema = load_protocol_schema(self.protocol_root, "State-Given", "DGC")
        result = analyze_output('{"mode":"execution"}', schema)
        self.assertTrue(result["strict_json_valid"])
        self.assertFalse(result["schema_valid"])

    def test_prompt_schema_normalizer_matches_edge_formatting_repairs(self):
        schema = load_protocol_schema(self.protocol_root, "State-Given", "DGC")
        raw = json.dumps(
            {"actions": [
                {
                    "arguments": {
                        "device_id": "d1",
                        "service": "turn_on",
                        "arguments": {},
                    }
                }
            ]}
        )
        result = analyze_output(raw, schema)
        self.assertFalse(result["raw_schema_valid"])
        self.assertTrue(result["schema_valid"])
        self.assertTrue(result["normalization_used"])
        self.assertEqual("execution", result["parsed"]["mode"])
        self.assertEqual("d1", result["parsed"]["actions"][0]["device_id"])
        self.assertIn("added_mode", result["normalization_note"])
        self.assertIn("lifted_device_id", result["normalization_note"])

    def test_repair_prompt_carries_error_and_bounded_previous_output(self):
        prompt = generic_repair_instruction("x" * 2500, "$.mode:required")
        self.assertIn("$.mode:required", prompt)
        self.assertIn("上一次输出=" + "x" * 2000, prompt)
        self.assertNotIn("x" * 2001, prompt)


if __name__ == "__main__":
    unittest.main()
