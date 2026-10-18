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
from common.task_families import PUBLIC_INTERFACES, TASK_FAMILIES, interface_slug, normalize_task_family


def run_checked(command: list[str]) -> None:
    print("[server-full]", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the full EdgeBench Home State-Given/State-Seeking suite through an OpenAI-compatible local server."
    )
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env", default="VLLM_API_KEY")
    parser.add_argument("--tokenizer-json")
    parser.add_argument("--require-exact-tokenizer", action="store_true")
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
    parser.add_argument("--max-context-len", type=int, default=16384)
    parser.add_argument("--state-given-max-new-tokens", type=int, default=1024)
    parser.add_argument("--state-seeking-max-new-tokens", type=int, default=512)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--request-timeout", type=float, default=900.0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--no-score", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    task_families = [normalize_task_family(value) for value in args.task_families]

    args.output_root.mkdir(parents=True, exist_ok=True)
    run_config_path = args.output_root / "benchmark_run_config.json"
    run_config = {
        "schema_version": "edgehome-server-benchmark-run-v1",
        "suite": "EdgeBench",
        "module": "Home",
        "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id,
        "suite_root": str(args.suite_root.resolve()),
        "base_url": args.base_url,
        "model": args.model,
        "protocol_profile": args.protocol_profile,
        "interfaces": list(args.interfaces),
        "task_families": task_families,
        "language": args.language,
        "max_context_len": args.max_context_len,
        "state_given_max_new_tokens": args.state_given_max_new_tokens,
        "state_seeking_max_new_tokens": args.state_seeking_max_new_tokens,
        "max_steps": args.max_steps,
        "temperature": args.temperature,
        "seed": args.seed,
    }
    run_config_path.write_text(json.dumps(run_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
                str(REPO_ROOT / "server" / entrypoint),
                "--run-id", f"{args.run_id}_{family}_{public_interface}",
                "--protocol-profile", args.protocol_profile,
                "--input", str(source),
                "--output", str(output),
                "--protocol-root", str(protocol_root(args.suite_root, interface, language=args.language)),
                "--base-url", args.base_url,
                "--model", args.model,
                "--api-key-env", args.api_key_env,
                "--max-context-len", str(args.max_context_len),
                "--max-new-tokens", str(args.state_given_max_new_tokens if internal_interface == "dr" else args.state_seeking_max_new_tokens),
                "--request-timeout", str(args.request_timeout),
                "--temperature", str(args.temperature),
            ]
            if internal_interface == "eia":
                command.extend(["--suite-root", str(args.suite_root), "--max-steps", str(args.max_steps)])
            if args.tokenizer_json:
                command.extend(["--tokenizer-json", args.tokenizer_json])
            if args.require_exact_tokenizer:
                command.append("--require-exact-tokenizer")
            if args.seed is not None:
                command.extend(["--seed", str(args.seed)])
            run_checked(command)

    if not args.no_score:
        for interface in args.interfaces:
            internal_interface = "dr" if interface == "State-Given" else "eia"
            public_interface = interface_slug(interface)
            command = [
                sys.executable,
                str(REPO_ROOT / "scoring" / "unified_scorer.py"),
                "--suite-root", str(args.suite_root),
                "--interface", public_interface,
                "--predictions", *[str(path) for path in prediction_files[interface]],
                "--output-dir", str(args.output_root / "scores" / public_interface),
            ]
            if args.require_complete:
                command.append("--require-complete")
            run_checked(command)
        run_config["status"] = "complete"
    else:
        run_config["status"] = "inference_complete"
    run_config["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    run_config_path.write_text(json.dumps(run_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
