from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from common.dataset_layout import input_path, protocol_root
from common.task_families import (
    PUBLIC_INTERFACES,
    TASK_FAMILIES,
    interface_slug,
    normalize_task_family,
)


def complete_existing(output: Path, source: Path) -> bool:
    """Return whether output contains the same ordered case IDs as source."""
    if not output.is_file() or not source.is_file():
        return False
    try:
        def ids(path: Path) -> list[str]:
            return [json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return ids(output) == ids(source)
    except (OSError, KeyError, json.JSONDecodeError):
        return False


def run_checked(command: list[str]) -> None:
    print("[edge-full]", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run EdgeBench Home State-Given/State-Seeking inputs, then invoke the unified scorer."
    )
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--interfaces", nargs="+", choices=PUBLIC_INTERFACES, default=PUBLIC_INTERFACES
    )
    parser.add_argument("--task-families", nargs="+", choices=TASK_FAMILIES, default=TASK_FAMILIES)
    parser.add_argument("--language", default="zh", choices=("zh", "en"))
    parser.add_argument(
        "--protocol-profile",
        choices=("P0_prompt_only", "P2_prompt_schema_repair1"),
        default="P0_prompt_only",
    )
    parser.add_argument("--binary", required=True)
    parser.add_argument("--rkllm-model", required=True)
    parser.add_argument("--model-sha256")
    parser.add_argument("--ld-library-path", required=True)
    parser.add_argument("--tokenizer-path", required=True)
    parser.add_argument("--max-context-len", type=int, default=16384)
    parser.add_argument("--state-given-max-new-tokens", type=int, default=1024)
    parser.add_argument("--state-seeking-max-new-tokens", type=int, default=512)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--startup-timeout", type=float, default=300.0)
    parser.add_argument("--request-timeout", type=float, default=900.0)
    parser.add_argument("--metrics-sample-interval-ms", type=int, default=100)
    parser.add_argument("--no-board-metrics", action="store_true")
    parser.add_argument("--no-score", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    task_families = [normalize_task_family(value) for value in args.task_families]
    args.output_root.mkdir(parents=True, exist_ok=True)
    benchmark_config_path = args.output_root / "benchmark_run_config.json"
    benchmark_config = {
        "schema_version": "edgehome-edge-benchmark-run-v1",
        "suite": "EdgeBench",
        "module": "Home",
        "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id,
        "suite_root": str(args.suite_root.resolve()),
        "interfaces": list(args.interfaces),
        "task_families": task_families,
        "language": args.language,
        "protocol_profile": args.protocol_profile,
        "binary": args.binary,
        "rkllm_model": args.rkllm_model,
        "model_sha256": args.model_sha256,
        "ld_library_path": args.ld_library_path,
        "tokenizer_path": args.tokenizer_path,
        "max_context_len": args.max_context_len,
        "state_given_max_new_tokens": args.state_given_max_new_tokens,
        "state_seeking_max_new_tokens": args.state_seeking_max_new_tokens,
        "max_steps": args.max_steps,
        "startup_timeout": args.startup_timeout,
        "request_timeout": args.request_timeout,
        "collect_board_metrics": not args.no_board_metrics,
        "metrics_sample_interval_ms": args.metrics_sample_interval_ms,
    }
    benchmark_config_path.write_text(
        json.dumps(benchmark_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    prediction_files: dict[str, list[Path]] = {"State-Given": [], "State-Seeking": []}
    for interface in args.interfaces:
        internal_interface = "dr" if interface == "State-Given" else "eia"
        public_interface = interface_slug(interface)
        entrypoint = "run_state_given.py" if interface == "State-Given" else "run_state_seeking.py"
        for family in task_families:
            source = input_path(args.suite_root, interface, family, language=args.language)
            output = args.output_root / "predictions" / public_interface / source.name
            prediction_files[interface].append(output)
            command = [
                sys.executable,
                str(REPO_ROOT / "edge" / entrypoint),
                "--run-id", f"{args.run_id}_{family}_{public_interface}",
                "--protocol-profile", args.protocol_profile,
                "--input", str(source),
                "--output", str(output),
                "--protocol-root", str(protocol_root(args.suite_root, interface, language=args.language)),
                "--binary", args.binary,
                "--rkllm-model", args.rkllm_model,
                "--ld-library-path", args.ld_library_path,
                "--tokenizer-path", args.tokenizer_path,
                "--max-context-len", str(args.max_context_len),
                "--max-new-tokens", str(
                    args.state_given_max_new_tokens if internal_interface == "dr" else args.state_seeking_max_new_tokens
                ),
                "--startup-timeout", str(args.startup_timeout),
                "--request-timeout", str(args.request_timeout),
                "--metrics-sample-interval-ms", str(args.metrics_sample_interval_ms),
            ]
            if internal_interface == "eia":
                command.extend(["--suite-root", str(args.suite_root), "--max-steps", str(args.max_steps)])
            if args.model_sha256:
                command.extend(["--model-sha256", args.model_sha256])
            if args.no_board_metrics:
                command.append("--no-board-metrics")
            run_checked(command)

    if args.no_score:
        benchmark_config.update(
            status="inference_complete",
            finished_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        benchmark_config_path.write_text(
            json.dumps(benchmark_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return 0

    for interface in args.interfaces:
        internal_interface = "dr" if interface == "State-Given" else "eia"
        public_interface = interface_slug(interface)
        command = [
            sys.executable,
            str(REPO_ROOT / "scoring" / "unified_scorer.py"),
            "--suite-root", str(args.suite_root),
            "--interface", public_interface,
            "--predictions",
            *[str(path) for path in prediction_files[interface]],
            "--output-dir", str(args.output_root / "scores" / public_interface),
        ]
        if args.require_complete:
            command.append("--require-complete")
        run_checked(command)
    benchmark_config.update(
        status="complete",
        finished_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    benchmark_config_path.write_text(
        json.dumps(benchmark_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
