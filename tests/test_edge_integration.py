from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from edge.board_metrics import BoardMetricsSampler
from edge.rkllm_model_client import PersistentRKLLMClient
from edge.run_full import complete_existing


ROOT = Path(__file__).resolve().parents[1]


class EdgeRuntimeAssetTests(unittest.TestCase):
    def test_p0_runtime_source_contains_wire_and_perf_markers(self):
        source = (ROOT / "edge/runtime/src/edgehome_rkllm_persistent.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("__EDGEHOME_READY__", source)
        self.assertIn("__EDGEHOME_RESULT__", source)
        self.assertIn("[edgehome-perf]", source)
        self.assertNotIn("\n    rkllm_set_function_tools(", source)

    def test_p2_runtime_source_contains_schema_audit_and_repair(self):
        source = (ROOT / "edge/runtime/src/rkllm_structured_persistent.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("__TEXT_LLM_READY__", source)
        self.assertIn("__STRUCTURED_AUDIT__", source)
        self.assertIn("schema_json_path", source)
        self.assertIn("格式纠正", source)

    def test_board_sampler_reports_unavailable_sensors_explicitly(self):
        sampler = BoardMetricsSampler(process_pid=0, interval_ms=20)
        sampler.start()
        time.sleep(0.03)
        summary = sampler.stop()
        self.assertGreaterEqual(summary["sample_count"], 2)
        self.assertIn("power_sensor_available", summary)
        self.assertIn("temperature_c", summary)
        self.assertIn("devfreq", summary)

    def test_resume_requires_same_ordered_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            output = root / "output.jsonl"
            source.write_text('{"id":"a"}\n{"id":"b"}\n', encoding="utf-8")
            output.write_text(
                '\n'.join((json.dumps({"id": "a"}), json.dumps({"id": "b"}))) + "\n",
                encoding="utf-8",
            )
            self.assertTrue(complete_existing(output, source))
            output.write_text('{"id":"b"}\n{"id":"a"}\n', encoding="utf-8")
            self.assertFalse(complete_existing(output, source))

    def test_p0_perf_log_is_normalized(self):
        parsed = PersistentRKLLMClient._parse_perf(
            [
                "[edgehome-perf] id=x role=user prefill_ms=500.0 prefill_tokens=50 "
                "prefill_tps=100.0 decode_ms=1000.0 decode_tokens=5 decode_tps=5.0 "
                "memory_mb=2300.5 kv_before=10 kv_after=65"
            ]
        )
        self.assertTrue(parsed["available"])
        self.assertEqual(50, parsed["prefill_tokens"])
        self.assertEqual(5.0, parsed["generate_tokens_per_second"])
        self.assertEqual(2300.5, parsed["peak_memory_usage_mb"])


if __name__ == "__main__":
    unittest.main()
