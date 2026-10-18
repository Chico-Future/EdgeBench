from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common.eia_environment import EIAEnvironment
from common.protocol import protocol_schema_path
from scoring.unified_scorer import aggregate, markdown_report
from common.task_families import (
    STATE_GIVEN,
    STATE_SEEKING,
    interface_slug,
    normalize_task_family,
)


class ReleasedLayoutTests(unittest.TestCase):
    def test_only_public_names_are_accepted(self):
        self.assertEqual("DGC", normalize_task_family("DGC"))
        with self.assertRaises(ValueError):
            normalize_task_family("tc1")
        with self.assertRaises(ValueError):
            normalize_task_family(1)
        self.assertEqual(STATE_GIVEN, interface_slug("State-Given"))
        self.assertEqual(STATE_SEEKING, interface_slug("State-Seeking"))

    def test_protocol_schema_uses_task_family_filename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / STATE_GIVEN / "protocols"
            root.mkdir(parents=True)
            schema = root / "DGC.json"
            schema.write_text("{}", encoding="utf-8")
            self.assertEqual(schema.resolve(), protocol_schema_path(Path(temporary), STATE_GIVEN, "DGC"))

    def test_released_environment_applies_spec_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "en" / "DGC" / "data"
            root.mkdir(parents=True)
            case_id = "dgc_en_test_001"
            case = {
                "id": case_id,
                "model_input": {
                    "home": {
                        "rooms": [],
                        "devices": [
                            {
                                "device_id": "light-1",
                                "spec_id": "light_v1",
                                "room_id": "room-1",
                                "state": {"power": "off", "settings": {"brightness": 20}},
                            }
                        ],
                    }
                },
            }
            specs = {
                "specs": {
                    "light_v1": {
                        "services": {
                            "set_brightness": {
                                "arguments": {"brightness": {"type": "integer"}},
                                "effects": {"settings.brightness": "$brightness"},
                                "preconditions": {"power": "on"},
                            }
                        }
                    }
                }
            }
            (root / "cases.jsonl").write_text(json.dumps(case) + "\n", encoding="utf-8")
            (root / "device_specs.json").write_text(json.dumps(specs), encoding="utf-8")
            environment = EIAEnvironment(Path(temporary), "DGC", case_id)
            environment.call("get_device_spec", {"device_id": "light-1"})
            self.assertFalse(environment.call("control_device", {
                "device_id": "light-1",
                "service": "set_brightness",
                "arguments": {"brightness": 80},
            })["ok"])
            environment.home["devices"][0]["state"]["power"] = "on"
            result = environment.call("control_device", {
                "device_id": "light-1",
                "service": "set_brightness",
                "arguments": {"brightness": 80},
            })
            self.assertTrue(result["ok"])
            self.assertEqual(80, environment.home["devices"][0]["state"]["settings"]["brightness"])

    def test_released_score_summary_uses_public_task_family_names(self):
        row = {
            "task_family": "DGC",
            "overall_pass": True,
            "lenient_overall_pass": True,
            "runtime_success": True,
            "trajectory_complete": True,
            "parse_success": True,
            "protocol_pass": True,
            "artifact_integrity": True,
            "errors": [],
            "source_diagnostics": {
                "protocol_profile": "P0_prompt_only",
                "strict_format_success": True,
                "first_pass_schema_success": True,
                "accepted_schema_success": True,
                "repair_used": False,
                "repair_attempts": 0,
                "model_turns": 1,
                "tool_calls": 0,
                "failed_tool_calls": 0,
                "duplicate_tool_calls": 0,
            },
        }
        summary = aggregate([row], STATE_GIVEN)
        self.assertIn("by_task_family", summary)
        self.assertNotIn("by_tc", summary)
        self.assertIn("DGC", summary["by_task_family"])
        self.assertNotIn("source_tc", summary)
        report = markdown_report(summary)
        self.assertIn("Task-family macro success", report)
        self.assertNotIn("TC macro success", report)


if __name__ == "__main__":
    unittest.main()
