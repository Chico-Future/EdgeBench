#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify dataset files against a supplied size and SHA256 manifest.")
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    failures: list[str] = []
    for entry in manifest["files"]:
        path = args.suite_root / entry["path"]
        if not path.is_file():
            failures.append(f"MISSING {entry['path']}")
            continue
        size = path.stat().st_size
        if size != entry["bytes"]:
            failures.append(f"SIZE {entry['path']}: {size} != {entry['bytes']}")
            continue
        actual = sha256(path)
        if actual != entry["sha256"]:
            failures.append(f"SHA256 {entry['path']}: {actual} != {entry['sha256']}")

    if failures:
        print("\n".join(failures))
        return 2
    print(f"SUITE MANIFEST OK: {len(manifest['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
