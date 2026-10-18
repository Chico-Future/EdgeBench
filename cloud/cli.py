from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cloud.backend import CloudTokenCounter, OpenAICompatibleBackend
from cloud.config import load_environment, resolve_model
from common.eia_common import read_jsonl
from common.manifest import file_sha256, write_run_manifest
from common.protocol import PROFILES, get_profile, load_protocol_schema
from common.runner_core import RunConfig, run_dr, run_eia, system_prompt_for_rows
from common.task_families import implementation_mode, task_family_for_rows


ROOT = Path(__file__).resolve().parents[1]


def _coalesce(value: Any, configured: Any, fallback: Any) -> Any:
    if value is not None:
        return value
    if configured is not None:
        return configured
    return fallback


def run(interface: str) -> None:
    parser = argparse.ArgumentParser(description=f"EdgeBench Home {interface} runner")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--suite-root", type=Path, required=implementation_mode(interface) == "eia")
    parser.add_argument("--protocol-root", type=Path, help="Override the dataset protocol directory")
    parser.add_argument("--protocol-profile", choices=tuple(PROFILES), default="P0_prompt_only")

    # Optional provider configuration path: .env + cloud/models.yaml + model key.
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--models-file", type=Path, default=ROOT / "cloud" / "models.yaml")
    parser.add_argument("--model-key")

    # Direct OpenAI-compatible arguments remain available for llama.cpp and
    # providers that are not represented in models.yaml.
    parser.add_argument("--base-url", help="OpenAI-compatible base URL ending in /v1")
    parser.add_argument("--model")
    parser.add_argument("--api-key-env")
    parser.add_argument("--tokenizer-json")
    parser.add_argument("--require-exact-tokenizer", action="store_true")
    parser.add_argument("--token-safety-factor", type=float, default=1.25)
    parser.add_argument("--max-new-tokens", type=int)
    parser.add_argument("--max-context-len", type=int)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--request-timeout", type=float)
    parser.add_argument("--max-tokens-field", choices=("max_tokens", "max_completion_tokens"))
    parser.add_argument(
        "--case-id",
        action="append",
        help="Run only the named case; repeat this option to select multiple cases.",
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    load_environment(args.env_file)

    configured = None
    if args.model_key:
        configured = resolve_model(
            args.models_file,
            args.model_key,
            env_file=args.env_file,
            profile=args.protocol_profile,
            interface=interface,
        )
    elif not args.base_url or not args.model:
        parser.error("use --model-key, or provide both --base-url and --model")

    base_url = args.base_url or configured.base_url
    model = args.model or configured.model
    api_key_env = args.api_key_env or (configured.api_key_env if configured else "OPENAI_API_KEY")
    if args.temperature is not None:
        temperature: float | None = float(args.temperature)
    elif configured is not None:
        temperature = configured.temperature
    else:
        temperature = 0.0
    request_timeout = float(
        _coalesce(args.request_timeout, configured.request_timeout if configured else None, 900.0)
    )
    max_tokens_field = str(
        _coalesce(args.max_tokens_field, configured.max_tokens_field if configured else None, "max_tokens")
    )
    max_context_len = int(
        _coalesce(args.max_context_len, configured.max_context_len if configured else None, 16384)
    )
    configured_output = configured.max_new_tokens[interface] if configured else None
    max_new_tokens = int(
        _coalesce(args.max_new_tokens, configured_output, 1024 if implementation_mode(interface) == "dr" else 512)
    )
    max_steps = int(_coalesce(args.max_steps, None, 20))
    seed = _coalesce(args.seed, configured.seed if configured else None, None)
    request_extra = configured.extra_body if configured else {}
    provider = configured.provider if configured else "direct_openai_compatible"

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
        protocol_root = candidate if (candidate / "protocols").is_dir() else ROOT / "protocols"
    schema = load_protocol_schema(protocol_root, interface, task_family)
    counter = CloudTokenCounter(
        args.tokenizer_json,
        safety_factor=args.token_safety_factor,
        schema=schema if profile.structured_output else None,
    )
    if args.require_exact_tokenizer and not counter.exact:
        raise RuntimeError("formal_run_requires_exact_tokenizer")
    config = RunConfig(
        interface=interface,
        profile=profile,
        max_new_tokens=max_new_tokens,
        max_context_len=max_context_len,
        max_steps=max_steps,
    )
    backend = OpenAICompatibleBackend(
        base_url=base_url,
        model=model,
        api_key_env=api_key_env,
        system_prompt=system_prompt,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        timeout=request_timeout,
        schema=schema if profile.structured_output else None,
        schema_transport=profile.schema_transport,
        max_tokens_field=max_tokens_field,
        seed=seed,
        request_extra=request_extra,
    )
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
            "provider": provider,
            "model_key": args.model_key,
            "models_file": str(args.models_file) if args.model_key else None,
            "base_url": base_url,
            "model": model,
            "api_key_env": api_key_env,
            "request_extra": request_extra,
            "schema_transport": profile.schema_transport,
            "tokenizer_json": args.tokenizer_json,
            "tokenizer_sha256": file_sha256(Path(args.tokenizer_json)) if args.tokenizer_json else None,
            "token_count_method": counter.method,
            "temperature": temperature,
            "seed": seed,
            "max_context_len": max_context_len,
            "max_new_tokens": max_new_tokens,
            "max_steps": max_steps if implementation_mode(interface) == "eia" else None,
            "request_timeout": request_timeout,
            "max_tokens_field": max_tokens_field,
            "case_ids": args.case_id,
        },
    )
    print(
        json.dumps(
            {
                "interface": interface,
                "profile": profile.name,
                "provider": provider,
                "model_key": args.model_key,
                "model": model,
                "records": len(records),
                "errors": sum(record.get("error") is not None for record in records),
                "output": str(args.output),
                "manifest": str(manifest),
            },
            ensure_ascii=False,
        )
    )
