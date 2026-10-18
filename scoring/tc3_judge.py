from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "edgehome-tc3-judge-v1"
PROMPT_VERSION = "tc3-clarification-judge-v1"
ALLOWED_QUALITIES = {"full", "partial", "fail"}
DEFAULT_PROMPT_PATH = Path(__file__).with_name("tc3_judge_prompt_v1.txt")
DEFAULT_JUDGES_PATH = Path(__file__).with_name("judges.yaml")
DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
JUDGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "quality": {"type": "string", "enum": ["full", "partial", "fail"]},
        "rationale": {"type": "string", "minLength": 1},
    },
    "required": ["quality", "rationale"],
    "additionalProperties": False,
}


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
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(compact_json(row) + "\n" for row in rows), encoding="utf-8"
    )
    temporary.replace(path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_index(path: Path) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(path)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = row.get("id")
        if not isinstance(case_id, str) or case_id in result:
            raise ValueError(f"invalid or duplicate id in {path}: {case_id}")
        result[case_id] = row
    return result


def load_prediction_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        for row in read_jsonl(path):
            case_id = row.get("id")
            if not isinstance(case_id, str) or case_id in seen:
                raise ValueError(f"invalid or duplicate prediction id: {case_id}")
            seen.add(case_id)
            rows.append(row)
    return rows


def extract_prediction(row: dict[str, Any], interface: str) -> dict[str, Any]:
    key = "prediction" if interface == "State-Given" else "final_output"
    value = row.get(key)
    return value if isinstance(value, dict) else {}


def validate_packet(packet: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "id",
        "interface",
        "response",
        "response_sha256",
        "source_record_sha256",
        "judge_input",
        "judge_input_sha256",
    }
    if set(packet) != required or packet.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"invalid judge packet fields for {packet.get('id')}")
    if packet.get("interface") not in {"State-Given", "State-Seeking"}:
        raise ValueError(f"invalid interface for {packet.get('id')}")
    response = packet.get("response")
    if not isinstance(response, str) or not response.strip():
        raise ValueError(f"missing response for {packet.get('id')}")
    if packet.get("response_sha256") != object_sha256(response):
        raise ValueError(f"response hash mismatch for {packet.get('id')}")
    judge_input = packet.get("judge_input")
    if not isinstance(judge_input, dict) or set(judge_input) != {
        "user_visible_context",
        "ambiguity",
        "clarification_rubric",
        "candidate_response",
    }:
        raise ValueError(f"invalid judge input for {packet.get('id')}")
    if judge_input["candidate_response"] != response:
        raise ValueError(f"candidate response mismatch for {packet.get('id')}")
    if packet.get("judge_input_sha256") != object_sha256(judge_input):
        raise ValueError(f"judge input hash mismatch for {packet.get('id')}")


def prepare_packets(
    suite_root: Path,
    interface: str,
    prediction_paths: list[Path],
    output_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    if interface not in {"State-Given", "State-Seeking"}:
        raise ValueError(f"invalid interface: {interface}")
    roots = [suite_root / language for language in ("en", "zh")
             if (suite_root / language).is_dir()]
    if not roots:
        roots = [suite_root]  # Accept a single language directory too.
    cases: dict[str, dict[str, Any]] = {}
    evaluations: dict[str, dict[str, Any]] = {}
    dataset_files = []
    for root in roots:
        paths = [root / "AIR" / "data" / name
                 for name in ("cases.jsonl", "evaluation.jsonl")]
        language_cases, language_evaluations = map(load_index, paths)
        if set(language_cases) != set(language_evaluations):
            raise ValueError(f"AIR case/evaluation ID mismatch: {root}")
        duplicates = set(cases) & set(language_cases)
        if duplicates:
            raise ValueError(f"duplicate AIR IDs across languages: {sorted(duplicates)}")
        cases.update(language_cases)
        evaluations.update(language_evaluations)
        dataset_files.extend({"path": str(path.resolve()), "sha256": file_sha256(path)}
                             for path in paths)
    rows = load_prediction_rows(prediction_paths)
    packets: list[dict[str, Any]] = []
    skipped: dict[str, str] = {}

    for row in rows:
        case_id = row["id"]
        evaluation = evaluations.get(case_id)
        case = cases.get(case_id)
        if evaluation is None or case is None:
            continue
        if evaluation.get("expected_mode") != "clarification":
            skipped[case_id] = "not_a_clarification_gold_case"
            continue
        prediction = extract_prediction(row, interface)
        response = prediction.get("response")
        if prediction.get("mode") != "clarification":
            skipped[case_id] = "submitted_mode_is_not_clarification"
            continue
        if not isinstance(response, str) or not response.strip():
            skipped[case_id] = "clarification_response_missing"
            continue

        judge_input = {
            "user_visible_context": case["model_input"],
            "ambiguity": evaluation["ambiguity"],
            "clarification_rubric": evaluation["clarification_rubric"],
            "candidate_response": response,
        }
        packet = {
            "schema_version": SCHEMA_VERSION,
            "id": case_id,
            "interface": interface,
            "response": response,
            "response_sha256": object_sha256(response),
            "source_record_sha256": object_sha256(row),
            "judge_input": judge_input,
            "judge_input_sha256": object_sha256(judge_input),
        }
        validate_packet(packet)
        packets.append(packet)

    packets.sort(key=lambda item: item["id"])
    write_jsonl(output_path, packets)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "operation": "prepare",
        "created_at_utc": utc_now(),
        "interface": interface,
        "suite_root": str(suite_root.resolve()),
        "dataset_files": dataset_files,
        "prompt_version": PROMPT_VERSION,
        "prediction_files": [
            {"path": str(path.resolve()), "sha256": file_sha256(path)}
            for path in prediction_paths
        ],
        "packet_file": {
            "path": str(output_path.resolve()),
            "sha256": file_sha256(output_path),
            "count": len(packets),
        },
        "skipped": skipped,
    }
    write_json(manifest_path, manifest)
    return manifest


def validate_review(review: dict[str, Any], packet: dict[str, Any]) -> None:
    if set(review) != {"id", "response_sha256", "quality", "rationale"}:
        raise ValueError(f"invalid review fields for {review.get('id')}")
    if review.get("id") != packet["id"]:
        raise ValueError(f"review id mismatch for {packet['id']}")
    if review.get("response_sha256") != packet["response_sha256"]:
        raise ValueError(f"review response hash mismatch for {packet['id']}")
    if review.get("quality") not in ALLOWED_QUALITIES:
        raise ValueError(f"invalid quality for {packet['id']}")
    if not isinstance(review.get("rationale"), str) or not review["rationale"].strip():
        raise ValueError(f"missing rationale for {packet['id']}")


def validate_files(
    packet_path: Path, review_path: Path, require_complete: bool = False
) -> dict[str, Any]:
    packets = load_index(packet_path)
    reviews = load_index(review_path)
    for packet in packets.values():
        validate_packet(packet)
    unknown = sorted(set(reviews) - set(packets))
    if unknown:
        raise ValueError(f"reviews contain unknown ids: {unknown}")
    for case_id, review in reviews.items():
        validate_review(review, packets[case_id])
    missing = sorted(set(packets) - set(reviews))
    if require_complete and missing:
        raise ValueError(f"missing {len(missing)} reviews")
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_count": len(packets),
        "review_count": len(reviews),
        "missing_count": len(missing),
        "missing_ids": missing,
        "complete": not missing,
    }


def usage_to_dict(usage: Any) -> Any:
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    return str(usage)


def load_judge_config(
    path: Path, judge_key: str | None, require_credentials: bool = True
) -> tuple[str, dict[str, Any]]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("Install PyYAML to load the judge catalog") from exc

    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("unsupported_judges_yaml_version")
    judges = value.get("judges")
    if not isinstance(judges, dict) or not judges:
        raise ValueError("judges_yaml_has_no_judges")
    resolved_key = judge_key or value.get("default_judge")
    if not isinstance(resolved_key, str) or resolved_key not in judges:
        raise ValueError(f"unknown_judge_key:{resolved_key}")
    source = judges[resolved_key]
    if not isinstance(source, dict):
        raise ValueError(f"invalid_judge_config:{resolved_key}")

    required = {"provider", "api_style", "api_key_env", "model"}
    missing = sorted(required - set(source))
    if missing:
        raise ValueError(f"judge_config_missing_fields:{resolved_key}:{missing}")
    if source["api_style"] != "responses":
        raise ValueError(f"unsupported_judge_api_style:{source['api_style']}")
    if not source.get("enabled", False):
        raise ValueError(f"judge_is_disabled:{resolved_key}")

    base_url_env = source.get("base_url_env")
    if base_url_env:
        base_url = os.environ.get(str(base_url_env), "").strip()
        if not base_url:
            raise RuntimeError(f"missing_environment_variable:{base_url_env}")
    else:
        base_url = str(source.get("base_url", "")).strip()
    if not base_url:
        raise ValueError(f"judge_base_url_missing:{resolved_key}")

    api_key_env = str(source["api_key_env"])
    if require_credentials and not os.environ.get(api_key_env, "").strip():
        raise RuntimeError(f"missing_environment_variable:{api_key_env}")

    config = dict(source)
    config["base_url"] = base_url.rstrip("/")
    config["api_key_env"] = api_key_env
    config["temperature"] = float(config.get("temperature", 0.0))
    config["max_output_tokens"] = int(config.get("max_output_tokens", 300))
    config["reasoning_effort"] = config.get("reasoning_effort")
    config["strict_schema"] = bool(config.get("strict_schema", False))
    config["rolling_alias"] = bool(config.get("rolling_alias", False))
    return resolved_key, config


def run_responses_judge(
    packet_path: Path,
    review_path: Path,
    audit_path: Path,
    manifest_path: Path,
    prompt_path: Path,
    judges_path: Path,
    judge_key: str,
    judge_config: dict[str, Any],
    retries: int,
) -> dict[str, Any]:
    try:
        import openai
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the official openai Python package first") from exc

    prompt = prompt_path.read_text(encoding="utf-8").strip()
    packets = load_index(packet_path)
    for packet in packets.values():
        validate_packet(packet)

    existing_reviews = load_index(review_path) if review_path.exists() else {}
    existing_audits = load_index(audit_path) if audit_path.exists() else {}
    for case_id, review in existing_reviews.items():
        if case_id not in packets:
            raise ValueError(f"existing review has unknown id: {case_id}")
        validate_review(review, packets[case_id])

    model = str(judge_config["model"])
    temperature = float(judge_config["temperature"])
    max_output_tokens = int(judge_config["max_output_tokens"])
    reasoning_effort = judge_config.get("reasoning_effort")
    api_key_env = str(judge_config["api_key_env"])
    client = OpenAI(
        api_key=os.environ[api_key_env],
        base_url=str(judge_config["base_url"]),
    )
    started_at = utc_now()
    config = {
        "judge_key": judge_key,
        "provider": judge_config["provider"],
        "api_style": judge_config["api_style"],
        "base_url": judge_config["base_url"],
        "api_key_env": api_key_env,
        "requested_model": model,
        "rolling_alias": bool(judge_config.get("rolling_alias", False)),
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "reasoning_effort": reasoning_effort,
        "server_storage": False,
        "structured_output_schema_sha256": object_sha256(JUDGE_OUTPUT_SCHEMA),
    }

    def save(current_status: str) -> None:
        ordered_reviews = [existing_reviews[key] for key in sorted(existing_reviews)]
        ordered_audits = [existing_audits[key] for key in sorted(existing_audits)]
        write_jsonl(review_path, ordered_reviews)
        write_jsonl(audit_path, ordered_audits)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "operation": "run-responses-judge",
            "status": current_status,
            "started_at_utc": started_at,
            "updated_at_utc": utc_now(),
            "prompt_version": PROMPT_VERSION,
            "prompt_file": {
                "path": str(prompt_path.resolve()),
                "sha256": file_sha256(prompt_path),
            },
            "judge_catalog": {
                "path": str(judges_path.resolve()),
                "sha256": file_sha256(judges_path),
            },
            "packet_file": {
                "path": str(packet_path.resolve()),
                "sha256": file_sha256(packet_path),
                "count": len(packets),
            },
            "review_file": {
                "path": str(review_path.resolve()),
                "sha256": file_sha256(review_path),
                "count": len(existing_reviews),
            },
            "audit_file": {
                "path": str(audit_path.resolve()),
                "sha256": file_sha256(audit_path),
                "count": len(existing_audits),
            },
            "configuration": config,
            "openai_sdk_version": getattr(openai, "__version__", "unknown"),
            "resolved_models": sorted(
                {
                    row["resolved_model"]
                    for row in existing_audits.values()
                    if isinstance(row.get("resolved_model"), str)
                }
            ),
            "system_fingerprints": sorted(
                {
                    row["system_fingerprint"]
                    for row in existing_audits.values()
                    if isinstance(row.get("system_fingerprint"), str)
                }
            ),
        }
        write_json(manifest_path, manifest)

    save("running")
    for index, case_id in enumerate(sorted(packets), 1):
        packet = packets[case_id]
        if case_id in existing_reviews:
            print(f"[{index:03d}/{len(packets):03d}] SKIP {case_id}", flush=True)
            continue
        output_format: dict[str, Any] = {
            "type": "json_schema",
            "name": "tc3_clarification_review",
            "schema": JUDGE_OUTPUT_SCHEMA,
        }
        if judge_config.get("strict_schema"):
            output_format["strict"] = True
        request: dict[str, Any] = {
            "model": model,
            "instructions": prompt,
            "input": compact_json(packet["judge_input"]),
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "text": {"format": output_format},
        }
        if judge_config["provider"] == "openai":
            request["store"] = False
        if reasoning_effort is not None:
            request["reasoning"] = {"effort": reasoning_effort}

        last_error: Exception | None = None
        response = None
        for attempt in range(1, retries + 1):
            try:
                response = client.responses.create(**request)
                break
            except Exception as exc:  # API/network errors are recorded after retries.
                last_error = exc
                if attempt < retries:
                    time.sleep(min(2 ** (attempt - 1), 8))
        if response is None:
            save("failed")
            raise RuntimeError(f"judge request failed for {case_id}: {last_error}")

        parsed = json.loads(response.output_text)
        quality = parsed.get("quality")
        rationale = parsed.get("rationale")
        review = {
            "id": case_id,
            "response_sha256": packet["response_sha256"],
            "quality": quality,
            "rationale": rationale,
        }
        validate_review(review, packet)
        existing_reviews[case_id] = review
        existing_audits[case_id] = {
            "id": case_id,
            "response_sha256": packet["response_sha256"],
            "judge_input_sha256": packet["judge_input_sha256"],
            "prompt_sha256": file_sha256(prompt_path),
            "requested_model": model,
            "resolved_model": getattr(response, "model", None),
            "response_id": getattr(response, "id", None),
            "system_fingerprint": getattr(response, "system_fingerprint", None),
            "judge_output_sha256": object_sha256(parsed),
            "quality": quality,
            "rationale": rationale,
            "usage": usage_to_dict(getattr(response, "usage", None)),
            "completed_at_utc": utc_now(),
        }
        save("running")
        print(f"[{index:03d}/{len(packets):03d}] {quality.upper()} {case_id}", flush=True)

    save("completed")
    return validate_files(packet_path, review_path, require_complete=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare, run, and validate response-hash-bound EdgeBench-Home AIR clarification reviews."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--suite-root", type=Path, required=True)
    prepare.add_argument("--interface", choices=("State-Given", "State-Seeking"), required=True)
    prepare.add_argument("--predictions", type=Path, nargs="+", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--manifest", type=Path, required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--packets", type=Path, required=True)
    validate.add_argument("--reviews", type=Path, required=True)
    validate.add_argument("--require-complete", action="store_true")

    run = subparsers.add_parser("run-judge")
    run.add_argument("--packets", type=Path, required=True)
    run.add_argument("--reviews", type=Path, required=True)
    run.add_argument("--audit", type=Path, required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT_PATH)
    run.add_argument("--env-file", type=Path, default=DEFAULT_ENV_PATH)
    run.add_argument("--judges-file", type=Path, default=DEFAULT_JUDGES_PATH)
    run.add_argument("--judge-key")
    run.add_argument("--retries", type=int, default=3)

    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_packets(
            args.suite_root,
            args.interface,
            args.predictions,
            args.output,
            args.manifest,
        )
    elif args.command == "validate":
        result = validate_files(args.packets, args.reviews, args.require_complete)
    else:
        if args.env_file.exists():
            try:
                from dotenv import load_dotenv
            except ImportError as exc:
                raise RuntimeError("Install python-dotenv to load the judge env file") from exc
            load_dotenv(args.env_file, override=False)
        judge_key, judge_config = load_judge_config(
            args.judges_file, args.judge_key, require_credentials=True
        )
        result = run_responses_judge(
            args.packets,
            args.reviews,
            args.audit,
            args.manifest,
            args.prompt,
            args.judges_file,
            judge_key,
            judge_config,
            args.retries,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
