from __future__ import annotations

from pathlib import Path
from typing import Any

from .task_families import (
    STATE_GIVEN,
    STATE_SEEKING,
    interface_slug,
    normalize_task_family,
)


def language_root(dataset_root: Path, language: str | None = None) -> Path:
    """Return a language directory from the released package."""
    root = dataset_root.resolve()
    selected = language or "zh"
    candidate = root / selected
    if candidate.is_dir():
        return candidate
    raise FileNotFoundError(f"language dataset directory not found: {candidate}")


def input_path(
    dataset_root: Path,
    interface: Any,
    task_family: Any,
    *,
    language: str | None = None,
) -> Path:
    """Find one model-input JSONL in the released package."""
    family = normalize_task_family(task_family)
    root = language_root(dataset_root, language)
    public_interface = interface_slug(interface)
    path = root / public_interface / "data" / f"{family}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.resolve()


def protocol_root(
    dataset_root: Path,
    interface: Any,
    *,
    language: str | None = None,
) -> Path:
    """Return the directory containing released interface protocols when present."""
    root = language_root(dataset_root, language)
    candidate = root / interface_slug(interface)
    if (candidate / "protocols").is_dir():
        return candidate
    # The runner ships matching schemas when the dataset omits them.
    return Path(__file__).resolve().parents[1] / "protocols"


def interface_label(interface: Any) -> str:
    return STATE_GIVEN if interface_slug(interface) == STATE_GIVEN else STATE_SEEKING
