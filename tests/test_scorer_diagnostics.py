from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scoring" / "unified_scorer.py"
SPEC = importlib.util.spec_from_file_location("edgehome_unified_scorer_v3", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def source_row(
    profile: str, repairs: int, *, turns: int = 1, schema_transport: str | None = None
) -> dict:
    protocol = {"profile": profile, "schema_enforced": profile != "P0_prompt_only"}
    if schema_transport is not None:
        protocol["schema_transport"] = schema_transport
    return {
        "protocol": protocol,
        "format_diagnostics": {
            "first_strict_json_valid": repairs == 0,
            "first_schema_valid": repairs == 0,
            "accepted_schema_valid": True,
            "repair_used": repairs > 0,
            "repair_attempts": repairs,
            "profile_violations": [],
        },
        "telemetry": {"model_turns": turns},
    }


class ScorerDiagnosticsTests(unittest.TestCase):
    def test_prompt_p2_rejects_backend_schema_transport(self):
        result = MODULE.source_protocol_diagnostics(
            source_row(
                "P2_prompt_schema_repair1", 0, schema_transport="backend"
            ),
            "State-Given",
        )
        self.assertFalse(result["profile_compliant"])
        self.assertIn("schema_transport_mismatch", result["profile_violations"])

    def test_prompt_p2_accepts_prompt_schema_transport(self):
        result = MODULE.source_protocol_diagnostics(
            source_row("P2_prompt_schema_repair1", 1, schema_transport="prompt"),
            "State-Given",
        )
        self.assertTrue(result["profile_compliant"])

    def test_aggregate_reports_success_at_and_rejects_mixed_profiles(self):
        rows = []
        for index, (profile, turns) in enumerate(
            (("P0_prompt_only", 4), ("P2_prompt_schema_repair1", 12)), 1
        ):
            diagnostics = MODULE.source_protocol_diagnostics(source_row(profile, 0, turns=turns), "State-Given")
            rows.append(
                {
                    "task_family": "DGC" if index == 1 else "MSC",
                    "overall_pass": True,
                    "lenient_overall_pass": True,
                    "runtime_success": True,
                    "trajectory_complete": True,
                    "parse_success": True,
                    "protocol_pass": True,
                    "artifact_integrity": True,
                    "errors": [],
                    "source_diagnostics": diagnostics,
                }
            )
        summary = MODULE.aggregate(rows, "State-Given")
        self.assertEqual(0.5, summary["success_at"]["10"])
        self.assertTrue(summary["mixed_protocol_profiles"])
        self.assertFalse(summary["formal_report_ready"])


if __name__ == "__main__":
    unittest.main()
