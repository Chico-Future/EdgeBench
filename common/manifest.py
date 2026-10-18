from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .eia_common import write_json
from .protocol import schema_sha256


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_run_manifest(
    *,
    output: Path,
    run_id: str,
    interface: str,
    profile: str,
    backend: str,
    input_path: Path,
    schema: dict[str, Any],
    records: int,
    errors: int,
    configuration: dict[str, Any],
) -> Path:
    manifest_path = output.with_name(output.name + ".manifest.json")
    write_json(
        manifest_path,
        {
            "schema_version": "edgehome-run-manifest-v2",
            "suite": "EdgeBench",
            "module": "Home",
            "run_id": run_id,
            "interface": interface,
            "protocol_profile": profile,
            "backend": backend,
            "records": records,
            "errors": errors,
            "input": {
                "path": str(input_path.resolve()),
                "sha256": file_sha256(input_path),
            },
            "output": {
                "path": str(output.resolve()),
                "sha256": file_sha256(output),
            },
            "protocol_schema_sha256": schema_sha256(schema),
            "configuration": configuration,
        },
    )
    return manifest_path
