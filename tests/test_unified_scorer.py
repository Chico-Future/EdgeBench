from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scoring" / "unified_scorer.py"
SPEC = importlib.util.spec_from_file_location("edgehome_test_unified_scorer", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class UnifiedScorerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.suite_root = Path(temporary.name)
        action = {"device_id": "light-1", "service": "turn_on", "arguments": {}}
        change = {"device_id": "light-1", "path": "state.power", "before": "off", "after": "on"}
        rule = {"conditions": {"time_cron": "0 0 8 * * ? *", "state_expr": None}, "actions": [action]}
        for tc, family in enumerate(MODULE.TASK_FAMILIES, 1):
            case = {
                "id": f"{family.lower()}_en_synthetic",
                "task_family": family,
                "model_input": {
                    "request": "Turn on the light.",
                    "home": {"rooms": [], "devices": [{
                        "device_id": "light-1", "spec_id": "light_v1",
                        "state": {"power": "off"},
                    }]},
                },
            }
            evaluation = {
                "id": case["id"], "expected_mode": "execution",
                "reference_action": action, "reference_actions": [action],
                "ground_truth": {"expected_changes": [change]},
                "expected_state_delta": [{**change, "path": "power" if tc == 6 else "state.power"}],
                "reference_automations": [rule], "canonical_rules": [rule],
                "expected_result": {"answer_type": "count", "value": 1},
            }
            cases, evaluations = [case], [evaluation]
            if tc == 3:
                cases.append({**case, "id": "air_en_clarification"})
                evaluations.append({
                    "id": "air_en_clarification", "expected_mode": "clarification",
                    "reference_clarifications": ["Which light should I turn on?"],
                })
            data = self.suite_root / family / "data"
            MODULE.write_jsonl(data / "cases.jsonl", cases)
            MODULE.write_jsonl(data / "evaluation.jsonl", evaluations)
            MODULE.write_json(data / "device_specs.json", {"specs": {"light_v1": {
                "services": {"turn_on": {"arguments": {}, "effects": {"power": "on"}}},
            }}})
            for interface in ("State-Given", "State-Seeking"):
                MODULE.write_jsonl(self.suite_root / interface / "data" / f"{family}.jsonl", cases)
        self.scorer = MODULE.UnifiedScorer(self.suite_root)

    def _first_case(self, tc: int, predicate=lambda _row: True):
        for case_id, evaluation in self.scorer.evaluations[tc].items():
            if predicate(evaluation):
                return case_id, evaluation
        self.fail(f"no matching TC{tc} case")

    def test_reference_dr_predictions_pass_all_task_families(self):
        rows = []
        for tc in range(1, 8):
            if tc == 3:
                case_id, evaluation = self._first_case(
                    tc, lambda row: row["expected_mode"] == "execution"
                )
            else:
                case_id, evaluation = self._first_case(tc)

            if tc == 1:
                prediction = {"mode": "execution", "actions": [evaluation["reference_action"]]}
            elif tc in {2, 3, 5, 6}:
                prediction = {
                    "mode": "execution",
                    "actions": evaluation["reference_actions"],
                }
            elif tc == 4:
                prediction = {
                    "mode": "automation",
                    "automations": evaluation["reference_automations"],
                }
            else:
                prediction = {"mode": "answer", "result": evaluation["expected_result"]}
            rows.append(
                {
                    "id": case_id,
                    "task_family": MODULE.TASK_FAMILIES[tc - 1],
                    "prediction": prediction,
                    "error": None,
                }
            )

        results = [self.scorer.score_row(row, "State-Given") for row in rows]
        failures = [
            (row["id"], row["errors"], row["verification"])
            for row in results
            if row["overall_pass"] is not True
        ]
        self.assertEqual([], failures)
        summary = MODULE.aggregate(results, "State-Given")
        self.assertEqual(7, summary["passed_count"])
        self.assertEqual(1.0, summary["micro_success_rate"])
        self.assertEqual(1.0, summary["task_family_macro_success_rate"])

    def test_all_structured_reference_predictions_pass(self):
        rows = []
        clarification_rows = []
        for tc in range(1, 8):
            for case_id, evaluation in self.scorer.evaluations[tc].items():
                if tc == 1:
                    prediction = {"mode": "execution", "actions": [evaluation["reference_action"]]}
                elif tc in {2, 5, 6}:
                    prediction = {"mode": "execution", "actions": evaluation["reference_actions"]}
                elif tc == 3 and evaluation["expected_mode"] == "execution":
                    prediction = {"mode": "execution", "actions": evaluation["reference_actions"]}
                elif tc == 3:
                    prediction = {
                        "mode": "clarification",
                        "response": evaluation["reference_clarifications"][0],
                    }
                elif tc == 4:
                    prediction = {"mode": "automation", "automations": evaluation["reference_automations"]}
                else:
                    prediction = {"mode": "answer", "result": evaluation["expected_result"]}
                row = {
                    "id": case_id,
                    "task_family": MODULE.TASK_FAMILIES[tc - 1],
                    "prediction": prediction,
                    "error": None,
                }
                if tc == 3 and evaluation.get("expected_mode") == "clarification":
                    clarification_rows.append(row)
                else:
                    rows.append(row)

        results = [self.scorer.score_row(row, "State-Given") for row in rows]
        failures = [
            (row["id"], row["errors"], row["verification"])
            for row in results
            if row["overall_pass"] is not True
        ]
        self.assertEqual([], failures)

        pending = [self.scorer.score_row(row, "State-Given") for row in clarification_rows]
        self.assertTrue(pending)
        self.assertTrue(all(row["overall_pass"] is None for row in pending))
        self.assertTrue(
            all(row["verification"]["clarification_structural_pass"] for row in pending)
        )

    def test_eia_trace_replay_and_hash_check(self):
        case_id, evaluation = self._first_case(1)
        env = self.scorer._new_environment(1, case_id)
        action = evaluation["reference_action"]
        trace = []
        for name, arguments in (
            ("get_device_spec", {"device_id": action["device_id"]}),
            ("control_device", action),
        ):
            result = env.call(name, arguments)
            trace.append({"tool_name": name, "arguments": arguments, "result": result})
        row = {
            "id": case_id,
            "task_family": "DGC",
            "final_output": {"mode": "completed"},
            "tool_trace": trace,
            "initial_home_sha256": MODULE.object_sha256(env.initial_home),
            "final_home_sha256": MODULE.object_sha256(env.home),
            "error": None,
            "telemetry": {"model_turns": 3},
        }
        result = self.scorer.score_row(row, "State-Seeking")
        self.assertTrue(result["replay_integrity"])
        self.assertTrue(result["task_pass"])
        self.assertTrue(result["overall_pass"])
        self.assertTrue(result["replay_diagnostics"]["final_home_hash_match"])

    def test_eia_rejects_tampered_tool_result_and_environment_hash(self):
        case_id, _ = self._first_case(1)
        env = self.scorer._new_environment(1, case_id)
        result = self.scorer.score_row({
            "id": case_id, "task_family": "DGC",
            "final_output": {"mode": "completed"},
            "tool_trace": [{"tool_name": "get_device_spec",
                            "arguments": {"device_id": "light-1"},
                            "result": {"ok": False}}],
            "initial_home_sha256": MODULE.object_sha256(env.initial_home),
            "final_home_sha256": "0" * 64,
        }, "State-Seeking")
        self.assertFalse(result["replay_integrity"])
        self.assertFalse(result["overall_pass"])
        self.assertIn("tool_result_replay_mismatch", result["errors"])
        self.assertIn("environment_hash_mismatch", result["errors"])

    def test_air_review_for_different_response_remains_pending(self):
        case_id, _ = self._first_case(3, lambda row: row["expected_mode"] == "clarification")
        self.scorer.air_reviews[case_id] = {
            "id": case_id, "quality": "full", "rationale": "Synthetic review",
            "response_sha256": MODULE.value_digest("A different response"),
        }
        result = self.scorer.score_row({
            "id": case_id, "task_family": "AIR",
            "prediction": {"mode": "clarification", "response": "Which light?"},
        }, "State-Given")
        self.assertIsNone(result["overall_pass"])
        self.assertTrue(result["verification"]["semantic_review_pending"])
        self.assertFalse(result["verification"]["clarification_review_hash_match"])

    def test_incomplete_eia_trajectory_fails_without_runtime_failure(self):
        case_id, _evaluation = self._first_case(1)
        row = {
            "id": case_id,
            "task_family": "DGC",
            "final_output": None,
            "tool_trace": [],
            "error": "max_steps_exceeded",
        }
        result = self.scorer.score_row(row, "State-Seeking")
        self.assertTrue(result["runtime_success"])
        self.assertFalse(result["trajectory_complete"])
        self.assertFalse(result["protocol_pass"])
        self.assertFalse(result["overall_pass"])

    def test_tc7_requires_answer_mode_and_forbids_response_field(self):
        case_id, evaluation = self._first_case(7)
        expected = evaluation["expected_result"]
        base = {
            "id": case_id,
            "task_family": "REQ",
            "error": None,
        }

        valid = self.scorer.score_row(
            {**base, "prediction": {"mode": "answer", "result": expected}}, "State-Given"
        )
        self.assertTrue(valid["overall_pass"])
        self.assertTrue(valid["verification"]["output_schema_compliant"])

        wrong_mode = self.scorer.score_row(
            {**base, "prediction": {"mode": "completed", "result": expected}}, "State-Given"
        )
        self.assertFalse(wrong_mode["task_pass"])
        self.assertFalse(wrong_mode["overall_pass"])

        unexpected_response = self.scorer.score_row(
            {
                **base,
                "prediction": {
                    "mode": "answer",
                    "result": expected,
                    "response": "自然语言答案不属于TC7正式输出协议。",
                },
            },
            "State-Given",
        )
        self.assertFalse(unexpected_response["task_pass"])
        self.assertFalse(unexpected_response["overall_pass"])
        self.assertTrue(
            unexpected_response["verification"]["unexpected_response_present"]
        )

    def test_tc3_primary_is_strict_and_partial_is_lenient_only(self):
        case_id, evaluation = self._first_case(
            3, lambda row: row["expected_mode"] == "clarification"
        )
        response = evaluation["reference_clarifications"][0]
        prediction = {
            "id": case_id,
            "task_family": "AIR",
            "prediction": {"mode": "clarification", "response": response},
            "error": None,
        }

        with tempfile.TemporaryDirectory() as temporary:
            reviews_path = Path(temporary) / "reviews.jsonl"

            def score(quality: str):
                reviews_path.write_text(
                    json.dumps(
                        {
                            "id": case_id,
                            "response_sha256": MODULE.value_digest(response),
                            "quality": quality,
                            "rationale": "test review",
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n",
                    encoding="utf-8",
                )
                scorer = MODULE.UnifiedScorer(self.suite_root, reviews_path)
                return scorer.score_row(prediction, "State-Given")

            full = score("full")
            self.assertTrue(full["overall_pass"])
            self.assertTrue(full["lenient_overall_pass"])

            partial = score("partial")
            self.assertFalse(partial["overall_pass"])
            self.assertTrue(partial["lenient_overall_pass"])
            summary = MODULE.aggregate([partial], "State-Given")
            self.assertEqual(0.0, summary["micro_success_rate"])
            self.assertEqual(1.0, summary["lenient_micro_success_rate"])

    def test_invalid_tc3_structure_fails_without_pending_judge(self):
        case_id, _evaluation = self._first_case(
            3, lambda row: row["expected_mode"] == "clarification"
        )
        result = self.scorer.score_row(
            {
                "id": case_id,
                "task_family": "AIR",
                "prediction": {"mode": "execution", "actions": []},
                "error": None,
            },
            "State-Given",
        )
        self.assertFalse(result["verification"]["semantic_review_pending"])
        self.assertFalse(result["task_pass"])
        self.assertFalse(result["overall_pass"])

    def test_cli_writes_formal_ready_reports(self):
        case_id, evaluation = self._first_case(1)
        input_hash = self.scorer.interface_input_hashes["State-Given"][case_id]
        prediction = {
            "id": case_id,
            "task_family": "DGC",
            "input_record_sha256": input_hash,
            "prediction": {
                "mode": "execution",
                "actions": [evaluation["reference_action"]],
            },
            "error": None,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            predictions_path = root / "predictions.jsonl"
            output_dir = root / "score"
            predictions_path.write_text(
                json.dumps(prediction, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--suite-root",
                    str(self.suite_root),
                    "--interface",
                    "State-Given",
                    "--predictions",
                    str(predictions_path),
                    "--output-dir",
                    str(output_dir),
                    "--require-complete",
                ],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr + completed.stdout)
            self.assertTrue((output_dir / "score_records.jsonl").exists())
            self.assertTrue((output_dir / "summary.json").exists())
            self.assertTrue((output_dir / "report.md").exists())
            self.assertTrue((output_dir / "run_manifest.json").exists())
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["formal_report_ready"])
            self.assertEqual(1.0, summary["micro_success_rate"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
