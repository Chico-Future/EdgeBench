from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scoring" / "human_review.py"
SPEC = importlib.util.spec_from_file_location("edgehome_test_human_review", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class HumanReviewTests(unittest.TestCase):
    def packet(self, interface: str, response: str) -> dict:
        return {
            "id": "tc3_zh_002",
            "interface": interface,
            "response": response,
            "response_sha256": MODULE.object_sha256(response),
            "judge_input": {"candidate_response": response},
        }

    def test_blind_multi_system_and_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left, right = root / "left.jsonl", root / "right.jsonl"
            MODULE.write_jsonl(left, [self.packet("dr", "请问要打开哪台设备？")])
            MODULE.write_jsonl(right, [self.packet("dr", "主卧有两台设备，请指定。")])
            packets, mapping, template = root / "packets.jsonl", root / "mapping.jsonl", root / "template.jsonl"
            result = MODULE.prepare(
                [f"api/qwen/P0/dr={left}", f"server/qwen/P0/dr={right}"],
                packets, mapping, template,
            )
            self.assertEqual(2, result["count"])
            blinded = MODULE.read_jsonl(packets)
            self.assertTrue(all("system_id" not in row for row in blinded))
            reviews_a = [
                {"review_uid": row["review_uid"], "quality": "full", "rationale": "完整"}
                for row in blinded
            ]
            reviews_b = [dict(row) for row in reviews_a]
            reviewer_a, reviewer_b = root / "a.jsonl", root / "b.jsonl"
            MODULE.write_jsonl(reviewer_a, reviews_a)
            MODULE.write_jsonl(reviewer_b, reviews_b)
            final, disagreements, summary = root / "final.jsonl", root / "disagreements.jsonl", root / "summary.json"
            outcome = MODULE.adjudicate(
                packets, reviewer_a, reviewer_b, None, final, disagreements, summary
            )
            self.assertTrue(outcome["complete"])
            exported = MODULE.export_reviews(mapping, final, root / "exports")
            self.assertEqual(2, len(exported["systems"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
