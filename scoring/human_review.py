from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "edgehome-human-review-v1"
ALLOWED_QUALITIES = {"full", "partial", "fail"}


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def object_sha256(value: Any) -> str:
    return hashlib.sha256(compact_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(row)
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(compact_json(row) + "\n" for row in rows), encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError("--source must be SYSTEM_ID=PACKETS.jsonl")
    system_id, raw_path = value.split("=", 1)
    if not system_id.strip() or not raw_path.strip():
        raise ValueError("--source must be SYSTEM_ID=PACKETS.jsonl")
    return system_id.strip(), Path(raw_path)


def review_uid(system_id: str, packet: dict[str, Any]) -> str:
    identity = {
        "system_id": system_id,
        "interface": packet.get("interface"),
        "id": packet.get("id"),
        "response_sha256": packet.get("response_sha256"),
    }
    return object_sha256(identity)[:24]


def prepare(
    sources: list[str], packets_path: Path, mapping_path: Path, template_path: Path
) -> dict[str, Any]:
    blinded: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        system_id, path = parse_source(source)
        source_files.append({"system_id": system_id, "path": str(path.resolve()), "sha256": file_sha256(path)})
        for packet in read_jsonl(path):
            required = {"id", "interface", "response", "response_sha256", "judge_input"}
            if not required.issubset(packet):
                raise ValueError(f"invalid AIR packet in {path}: {packet.get('id')}")
            if object_sha256(packet["response"]) != packet["response_sha256"]:
                raise ValueError(f"response hash mismatch in {path}: {packet.get('id')}")
            uid = review_uid(system_id, packet)
            if uid in seen:
                raise ValueError(f"duplicate review_uid:{uid}")
            seen.add(uid)
            blinded.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "review_uid": uid,
                    "id": packet["id"],
                    "interface": packet["interface"],
                    "response": packet["response"],
                    "response_sha256": packet["response_sha256"],
                    "judge_input": packet["judge_input"],
                }
            )
            mapping_rows.append(
                {
                    "review_uid": uid,
                    "system_id": system_id,
                    "id": packet["id"],
                    "interface": packet["interface"],
                    "response_sha256": packet["response_sha256"],
                    "source_packet_sha256": object_sha256(packet),
                }
            )
    blinded.sort(key=lambda row: row["review_uid"])
    mapping_rows.sort(key=lambda row: row["review_uid"])
    template = [
        {"review_uid": row["review_uid"], "quality": "", "rationale": ""}
        for row in blinded
    ]
    write_jsonl(packets_path, blinded)
    write_jsonl(mapping_path, mapping_rows)
    write_jsonl(template_path, template)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "operation": "prepare",
        "created_at_utc": utc_now(),
        "blind_to_system_identity": True,
        "count": len(blinded),
        "source_files": source_files,
        "packets": {"path": str(packets_path.resolve()), "sha256": file_sha256(packets_path)},
        "mapping": {"path": str(mapping_path.resolve()), "sha256": file_sha256(mapping_path)},
        "reviewer_template": {"path": str(template_path.resolve()), "sha256": file_sha256(template_path)},
    }
    write_json(mapping_path.with_suffix(".manifest.json"), manifest)
    return manifest


def load_reviews(
    path: Path, expected: set[str], *, require_complete: bool = True
) -> dict[str, dict[str, Any]]:
    reviews: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        if set(row) != {"review_uid", "quality", "rationale"}:
            raise ValueError(f"invalid human review fields in {path}")
        uid = row.get("review_uid")
        if not isinstance(uid, str) or uid in reviews or uid not in expected:
            raise ValueError(f"invalid/duplicate/unknown review_uid in {path}:{uid}")
        if row.get("quality") not in ALLOWED_QUALITIES:
            raise ValueError(f"invalid quality in {path}:{uid}")
        if not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
            raise ValueError(f"missing rationale in {path}:{uid}")
        reviews[uid] = row
    missing = sorted(expected - set(reviews))
    if require_complete and missing:
        raise ValueError(f"{path} is missing {len(missing)} reviews")
    return reviews


def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> float | None:
    if not labels_a:
        return None
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / len(labels_a)
    counts_a, counts_b = Counter(labels_a), Counter(labels_b)
    expected = sum(
        (counts_a[label] / len(labels_a)) * (counts_b[label] / len(labels_b))
        for label in ALLOWED_QUALITIES
    )
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def adjudicate(
    packets_path: Path,
    reviewer_a_path: Path,
    reviewer_b_path: Path,
    adjudicator_path: Path | None,
    final_path: Path,
    disagreements_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    packet_rows = read_jsonl(packets_path)
    expected = {row["review_uid"] for row in packet_rows}
    if len(expected) != len(packet_rows):
        raise ValueError("duplicate review_uid in packets")
    reviewer_a = load_reviews(reviewer_a_path, expected)
    reviewer_b = load_reviews(reviewer_b_path, expected)
    adjudicator = (
        load_reviews(adjudicator_path, expected, require_complete=False)
        if adjudicator_path
        else {}
    )
    final_rows: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    labels_a, labels_b = [], []
    for uid in sorted(expected):
        left, right = reviewer_a[uid], reviewer_b[uid]
        labels_a.append(left["quality"])
        labels_b.append(right["quality"])
        if left["quality"] == right["quality"]:
            final_rows.append(
                {
                    "review_uid": uid,
                    "quality": left["quality"],
                    "rationale": f"Reviewer A: {left['rationale']} Reviewer B: {right['rationale']}",
                    "decision_source": "reviewer_agreement",
                }
            )
        elif uid in adjudicator:
            chosen = adjudicator[uid]
            final_rows.append(
                {
                    "review_uid": uid,
                    "quality": chosen["quality"],
                    "rationale": chosen["rationale"],
                    "decision_source": "adjudicator",
                }
            )
        else:
            disagreements.append({"review_uid": uid, "reviewer_a": left, "reviewer_b": right})
    write_jsonl(final_path, final_rows)
    write_jsonl(disagreements_path, disagreements)
    agreement = sum(a == b for a, b in zip(labels_a, labels_b)) / len(labels_a) if labels_a else None
    summary = {
        "schema_version": SCHEMA_VERSION,
        "operation": "adjudicate",
        "created_at_utc": utc_now(),
        "packet_count": len(expected),
        "final_count": len(final_rows),
        "disagreement_count": len(disagreements),
        "complete": len(final_rows) == len(expected),
        "raw_agreement": agreement,
        "cohen_kappa": cohen_kappa(labels_a, labels_b),
        "reviewer_a_sha256": file_sha256(reviewer_a_path),
        "reviewer_b_sha256": file_sha256(reviewer_b_path),
        "adjudicator_sha256": file_sha256(adjudicator_path) if adjudicator_path else None,
        "final_reviews_sha256": file_sha256(final_path),
    }
    write_json(summary_path, summary)
    return summary


def export_reviews(mapping_path: Path, final_path: Path, output_root: Path) -> dict[str, Any]:
    mapping = {row["review_uid"]: row for row in read_jsonl(mapping_path)}
    final_rows = read_jsonl(final_path)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for final in final_rows:
        uid = final.get("review_uid")
        if uid not in mapping:
            raise ValueError(f"unknown final review_uid:{uid}")
        source = mapping[uid]
        grouped.setdefault(source["system_id"], []).append(
            {
                "id": source["id"],
                "response_sha256": source["response_sha256"],
                "quality": final["quality"],
                "rationale": final["rationale"],
            }
        )
    files: dict[str, Any] = {}
    for system_id, rows in sorted(grouped.items()):
        safe_id = system_id.replace("/", "__").replace("\\", "__")
        path = output_root / safe_id / "reviews.jsonl"
        rows.sort(key=lambda row: row["id"])
        if len({row["id"] for row in rows}) != len(rows):
            raise ValueError(f"system has duplicate case IDs; export DR and EIA separately:{system_id}")
        write_jsonl(path, rows)
        files[system_id] = {"path": str(path.resolve()), "sha256": file_sha256(path), "count": len(rows)}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "operation": "export-scorer-reviews",
        "created_at_utc": utc_now(),
        "mapping_sha256": file_sha256(mapping_path),
        "final_reviews_sha256": file_sha256(final_path),
        "systems": files,
    }
    write_json(output_root / "export_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Blind two-reviewer AIR human review workflow.")
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--source", action="append", required=True, help="SYSTEM_ID=judge_packets.jsonl")
    prep.add_argument("--packets", type=Path, required=True)
    prep.add_argument("--mapping", type=Path, required=True)
    prep.add_argument("--reviewer-template", type=Path, required=True)
    adj = sub.add_parser("adjudicate")
    adj.add_argument("--packets", type=Path, required=True)
    adj.add_argument("--reviewer-a", type=Path, required=True)
    adj.add_argument("--reviewer-b", type=Path, required=True)
    adj.add_argument("--adjudicator", type=Path)
    adj.add_argument("--final", type=Path, required=True)
    adj.add_argument("--disagreements", type=Path, required=True)
    adj.add_argument("--summary", type=Path, required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--mapping", type=Path, required=True)
    exp.add_argument("--final", type=Path, required=True)
    exp.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.source, args.packets, args.mapping, args.reviewer_template)
    elif args.command == "adjudicate":
        result = adjudicate(
            args.packets, args.reviewer_a, args.reviewer_b, args.adjudicator,
            args.final, args.disagreements, args.summary,
        )
    else:
        result = export_reviews(args.mapping, args.final, args.output_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
