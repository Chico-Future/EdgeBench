from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scoring" / "tc3_judge.py"
SPEC = importlib.util.spec_from_file_location("edgehome_test_tc3_judge", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

class TC3JudgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.suite_root = Path(temporary.name)
        self.cases = {
            "air_zh_synthetic": {"id": "air_zh_synthetic", "model_input": {"request": "Turn on the bedroom device."}},
            "air_zh_execution": {"id": "air_zh_execution", "model_input": {"request": "Turn on the light."}},
        }
        self.evaluations = {
            "air_zh_synthetic": {
                "id": "air_zh_synthetic", "expected_mode": "clarification",
                "reference_clarifications": ["Which bedroom device?"],
                "ambiguity": {"type": "target_device"},
                "clarification_rubric": {"resolution_dimensions": ["target_device_if_single"]},
                "post_clarification_branches": [{"simulated_user_reply": "The light."}],
            },
            "air_zh_execution": {"id": "air_zh_execution", "expected_mode": "execution", "reference_actions": []},
        }
        data = self.suite_root / "AIR" / "data"
        data.mkdir(parents=True)
        MODULE.write_jsonl(data / "cases.jsonl", self.cases.values())
        MODULE.write_jsonl(data / "evaluation.jsonl", self.evaluations.values())

    def test_prepare_blind_hash_bound_packets(self):
        rows = []
        clarification_count = 0
        for case_id, evaluation in self.evaluations.items():
            if evaluation["expected_mode"] == "clarification":
                clarification_count += 1
                prediction = {
                    "mode": "clarification",
                    "response": evaluation["reference_clarifications"][0],
                }
            else:
                prediction = {"mode": "execution", "actions": evaluation["reference_actions"]}
            rows.append(
                {"id": case_id, "task_family": "AIR", "prediction": prediction, "error": None}
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            predictions = root / "predictions.jsonl"
            packets = root / "packets.jsonl"
            manifest = root / "prepare_manifest.json"
            MODULE.write_jsonl(predictions, rows)
            result = MODULE.prepare_packets(
                self.suite_root, "State-Given", [predictions], packets, manifest
            )
            packet_rows = MODULE.read_jsonl(packets)
            self.assertEqual(1, clarification_count)
            self.assertEqual(clarification_count, len(packet_rows))
            self.assertEqual(clarification_count, result["packet_file"]["count"])
            for packet in packet_rows:
                MODULE.validate_packet(packet)
                encoded = MODULE.compact_json(packet)
                self.assertNotIn("reference_clarifications", encoded)
                self.assertNotIn("post_clarification_branches", encoded)
                self.assertNotIn("simulated_user_reply", encoded)

    def test_disabled_catalog_requires_explicit_configuration(self):
        with self.assertRaisesRegex(ValueError, "judge_is_disabled"):
            MODULE.load_judge_config(MODULE_PATH.with_name("judges.yaml"), None)

    def test_synthetic_judge_config_resolves_credentials_offline(self):
        catalog = self.suite_root / "judges.yaml"
        catalog.write_text(
            "version: 1\ndefault_judge: synthetic\njudges:\n  synthetic:\n"
            "    provider: synthetic\n    api_style: responses\n"
            "    api_key_env: SYNTHETIC_JUDGE_KEY\n"
            "    base_url_env: SYNTHETIC_JUDGE_URL\n"
            "    model: synthetic-model\n    enabled: true\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {
            "SYNTHETIC_JUDGE_KEY": "test-only",
            "SYNTHETIC_JUDGE_URL": "https://judge.invalid/v1/",
        }):
            key, config = MODULE.load_judge_config(catalog, None)
        self.assertEqual("synthetic", key)
        self.assertEqual("synthetic-model", config["model"])
        self.assertEqual("https://judge.invalid/v1", config["base_url"])

    def test_review_validation_is_bound_to_exact_response(self):
        case_id, evaluation = next(
            (case_id, evaluation)
            for case_id, evaluation in self.evaluations.items()
            if evaluation["expected_mode"] == "clarification"
        )
        response = evaluation["reference_clarifications"][0]
        judge_input = {
            "user_visible_context": self.cases[case_id]["model_input"],
            "ambiguity": evaluation["ambiguity"],
            "clarification_rubric": evaluation["clarification_rubric"],
            "candidate_response": response,
        }
        packet = {
            "schema_version": MODULE.SCHEMA_VERSION,
            "id": case_id,
            "interface": "State-Given",
            "response": response,
            "response_sha256": MODULE.object_sha256(response),
            "source_record_sha256": "0" * 64,
            "judge_input": judge_input,
            "judge_input_sha256": MODULE.object_sha256(judge_input),
        }
        review = {
            "id": case_id,
            "response_sha256": packet["response_sha256"],
            "quality": "full",
            "rationale": "The missing target is directly requested.",
        }
        MODULE.validate_packet(packet)
        MODULE.validate_review(review, packet)
        review["response_sha256"] = MODULE.object_sha256(response + " changed")
        with self.assertRaises(ValueError):
            MODULE.validate_review(review, packet)

    def test_synthetic_clarification_packet_is_prepared_explicitly(self):
        case_id = "air_zh_synthetic"
        evaluation = self.evaluations[case_id]
        self.assertEqual("clarification", evaluation["expected_mode"])
        candidate = "你想启动主卧的哪一台设备？"
        row = {
            "id": case_id,
            "task_family": "AIR",
            "prediction": {"mode": "clarification", "response": candidate},
            "error": None,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            predictions = root / "predictions.jsonl"
            packets = root / "packets.jsonl"
            manifest = root / "prepare_manifest.json"
            MODULE.write_jsonl(predictions, [row])
            result = MODULE.prepare_packets(
                self.suite_root, "State-Given", [predictions], packets, manifest
            )
            packet_rows = MODULE.read_jsonl(packets)
            self.assertEqual(1, result["packet_file"]["count"])
            self.assertEqual(case_id, packet_rows[0]["id"])
            self.assertEqual(candidate, packet_rows[0]["judge_input"]["candidate_response"])
            self.assertEqual(
                ["target_device_if_single"],
                packet_rows[0]["judge_input"]["clarification_rubric"]["resolution_dimensions"],
            )

    def test_validate_files_reports_completion(self):
        case_id, evaluation = next(
            (case_id, evaluation)
            for case_id, evaluation in self.evaluations.items()
            if evaluation["expected_mode"] == "clarification"
        )
        response = evaluation["reference_clarifications"][0]
        judge_input = {
            "user_visible_context": self.cases[case_id]["model_input"],
            "ambiguity": evaluation["ambiguity"],
            "clarification_rubric": evaluation["clarification_rubric"],
            "candidate_response": response,
        }
        packet = {
            "schema_version": MODULE.SCHEMA_VERSION,
            "id": case_id,
            "interface": "State-Given",
            "response": response,
            "response_sha256": MODULE.object_sha256(response),
            "source_record_sha256": "0" * 64,
            "judge_input": judge_input,
            "judge_input_sha256": MODULE.object_sha256(judge_input),
        }
        review = {
            "id": case_id,
            "response_sha256": packet["response_sha256"],
            "quality": "partial",
            "rationale": "Relevant but underspecified.",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packets = root / "packets.jsonl"
            reviews = root / "reviews.jsonl"
            MODULE.write_jsonl(packets, [packet])
            MODULE.write_jsonl(reviews, [review])
            result = MODULE.validate_files(packets, reviews, require_complete=True)
            self.assertTrue(result["complete"])
            self.assertEqual(1, result["review_count"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
