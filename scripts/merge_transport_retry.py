from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRANSIENT_TRANSPORT_ERROR_PREFIXES = (
    "RuntimeError: transport_error:",
    "RuntimeError: http_error:500:",
    "RuntimeError: http_error:502:",
    "RuntimeError: http_error:503:",
    "RuntimeError: http_error:504:",
    "RemoteDisconnected:",
    "ConnectionResetError:",
    "TimeoutError:",
)


def is_transient_transport_error(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(
        TRANSIENT_TRANSPORT_ERROR_PREFIXES
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or not isinstance(value.get("id"), str):
                raise ValueError(f"invalid_record:{path}:{line_number}")
            rows.append(value)
    return rows


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replace one transient transport-error record with its audited retry."
    )
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--retry", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    original_rows = read_jsonl(args.original)
    retry_rows = read_jsonl(args.retry)
    original_matches = [row for row in original_rows if row["id"] == args.case_id]
    retry_matches = [row for row in retry_rows if row["id"] == args.case_id]
    if len(original_matches) != 1:
        raise ValueError(f"original_case_count:{len(original_matches)}")
    if len(retry_rows) != 1 or len(retry_matches) != 1:
        raise ValueError("retry_file_must_contain_exactly_the_requested_case")

    original_record = original_matches[0]
    retry_record = retry_matches[0]
    original_error = original_record.get("error")
    retry_error = retry_record.get("error")
    if not is_transient_transport_error(original_error):
        raise ValueError("original_record_is_not_a_transport_error")
    if is_transient_transport_error(retry_error):
        raise ValueError("retry_still_has_transport_error")
    if original_record.get("input_record_sha256") != retry_record.get(
        "input_record_sha256"
    ):
        raise ValueError("retry_input_record_sha256_mismatch")
    if original_record.get("protocol") != retry_record.get("protocol"):
        raise ValueError("retry_protocol_mismatch")

    merged = [retry_record if row["id"] == args.case_id else row for row in original_rows]
    if len(merged) != len(original_rows):
        raise AssertionError("record_count_changed")
    write_jsonl(args.output, merged)

    manifest = {
        "schema_version": "edgehome-transport-retry-merge-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "policy": "replace_exactly_one_transient_transport_error;never_select_by_score",
        "case_id": args.case_id,
        "original_error": original_error,
        "retry_error": retry_error,
        "original": {
            "path": str(args.original.resolve()),
            "sha256": file_sha256(args.original),
            "records": len(original_rows),
        },
        "retry": {
            "path": str(args.retry.resolve()),
            "sha256": file_sha256(args.retry),
            "records": len(retry_rows),
        },
        "output": {
            "path": str(args.output.resolve()),
            "sha256": file_sha256(args.output),
            "records": len(merged),
        },
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
