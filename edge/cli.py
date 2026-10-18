from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.eia_common import read_jsonl
from common.manifest import file_sha256, write_run_manifest
from common.protocol import get_profile, load_protocol_schema, protocol_schema_path
from common.runner_core import RunConfig, run_dr, run_eia, system_prompt_for_rows
from common.task_families import implementation_mode, task_family_for_rows
from edge.backend import (
    PromptRKLLMBackend,
    SchemaAwareTokenCounter,
    StructuredRKLLMBackend,
    TokenCounter,
)


EDGE_PROFILES = ("P0_prompt_only", "P2_prompt_schema_repair1")


def run(interface: str) -> None:
    parser = argparse.ArgumentParser(description=f"EdgeBench Home {interface} runner")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--suite-root", type=Path, required=implementation_mode(interface) == "eia")
    parser.add_argument("--protocol-root", type=Path, help="Override the dataset protocol directory")
    parser.add_argument("--protocol-profile", choices=EDGE_PROFILES, default="P0_prompt_only")
    parser.add_argument("--binary", required=True)
    parser.add_argument("--rkllm-model", required=True)
    parser.add_argument("--model-sha256", help="Avoid re-hashing a multi-GB model during every run")
    parser.add_argument("--ld-library-path", required=True)
    parser.add_argument("--tokenizer-path", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=1024 if implementation_mode(interface) == "dr" else 512)
    parser.add_argument("--max-context-len", type=int, default=16384)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--startup-timeout", type=float, default=300.0)
    parser.add_argument("--request-timeout", type=float, default=900.0)
    parser.add_argument(
        "--metrics-sample-interval-ms",
        type=int,
        default=100,
        help="RK3588 kernel telemetry sampling interval; default: 100 ms.",
    )
    parser.add_argument(
        "--no-board-metrics",
        action="store_true",
        help="Disable per-turn temperature/frequency/memory/power sampling.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        help="Run only the named case; repeat this option to select multiple cases.",
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    if args.case_id:
        wanted = set(args.case_id)
        available = {row["id"] for row in rows}
        missing = sorted(wanted - available)
        if missing:
            raise ValueError(f"case_id_not_found:{','.join(missing)}")
        rows = [row for row in rows if row["id"] in wanted]
    if args.limit is not None:
        rows = rows[: args.limit]
    if not rows:
        raise ValueError("empty_input")
    task_family = task_family_for_rows(rows)
    system_prompt = system_prompt_for_rows(rows)
    profile = get_profile(args.protocol_profile)
    protocol_root = args.protocol_root
    if protocol_root is None:
        candidate = args.input.resolve().parent.parent
        protocol_root = candidate if (candidate / "protocols").is_dir() else Path(__file__).resolve().parents[1] / "protocols"
    schema_path = protocol_schema_path(protocol_root, interface, task_family)
    schema = load_protocol_schema(protocol_root, interface, task_family)
    base_counter = TokenCounter(args.tokenizer_path)
    config = RunConfig(
        interface=interface,
        profile=profile,
        max_new_tokens=args.max_new_tokens,
        max_context_len=args.max_context_len,
        max_steps=args.max_steps,
    )
    backend_kwargs = dict(
        binary=args.binary,
        model=args.rkllm_model,
        max_new_tokens=args.max_new_tokens,
        max_context_len=args.max_context_len,
        ld_library_path=args.ld_library_path,
        system_prompt=system_prompt,
        startup_timeout=args.startup_timeout,
        request_timeout=args.request_timeout,
        collect_board_metrics=not args.no_board_metrics,
        metrics_sample_interval_ms=args.metrics_sample_interval_ms,
    )
    if profile.structured_output:
        backend = StructuredRKLLMBackend(**backend_kwargs, schema_path=schema_path)
        counter = SchemaAwareTokenCounter(base_counter, schema)
    else:
        backend = PromptRKLLMBackend(**backend_kwargs)
        counter = base_counter

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with backend:
        if implementation_mode(interface) == "dr":
            records = run_dr(rows, args.output, backend, counter, config, schema)
        else:
            records = run_eia(rows, args.output, args.suite_root, backend, counter, config, schema)
    manifest = write_run_manifest(
        output=args.output,
        run_id=args.run_id,
        interface=interface,
        profile=profile.name,
        backend=backend.backend_name,
        input_path=args.input,
        schema=schema,
        records=len(records),
        errors=sum(record.get("error") is not None for record in records),
        configuration={
            "model_path": args.rkllm_model,
            "model_sha256": args.model_sha256,
            "binary_path": args.binary,
            "binary_sha256": file_sha256(Path(args.binary)),
            "tokenizer_path": args.tokenizer_path,
            "token_count_method": counter.method,
            "schema_transport": profile.schema_transport,
            "max_context_len": args.max_context_len,
            "max_new_tokens": args.max_new_tokens,
            "max_steps": args.max_steps if implementation_mode(interface) == "eia" else None,
            "startup_timeout": args.startup_timeout,
            "request_timeout": args.request_timeout,
            "collect_board_metrics": not args.no_board_metrics,
            "metrics_sample_interval_ms": args.metrics_sample_interval_ms,
            "startup_wall_latency_ms": backend.client.startup_wall_latency_ms,
            "startup_log": backend.client.startup_log,
            "startup_board_metrics": backend.client.startup_board_metrics,
            "case_ids": args.case_id,
        },
    )
    print(
        json.dumps(
            {
                "interface": interface,
                "profile": profile.name,
                "records": len(records),
                "errors": sum(record.get("error") is not None for record in records),
                "output": str(args.output),
                "manifest": str(manifest),
            },
            ensure_ascii=False,
        )
    )
