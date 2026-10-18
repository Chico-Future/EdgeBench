from __future__ import annotations

from typing import Any


TASK_FAMILIES = ("DGC", "MSC", "AIR", "FAR", "DCR", "PMU", "REQ")
FAMILY_TO_INDEX = {family: index for index, family in enumerate(TASK_FAMILIES, 1)}

STATE_GIVEN = "State-Given"
STATE_SEEKING = "State-Seeking"
PUBLIC_INTERFACES = (STATE_GIVEN, STATE_SEEKING)


def normalize_task_family(value: Any) -> str:
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned in FAMILY_TO_INDEX:
            return cleaned
    raise ValueError(f"unsupported_task_family:{value}")


def task_family_index(value: Any) -> int:
    return FAMILY_TO_INDEX[normalize_task_family(value)]


def task_family_for_rows(rows: list[dict[str, Any]]) -> str:
    values = {
        normalize_task_family(row.get("task_family"))
        for row in rows
    }
    if len(values) != 1:
        raise ValueError("one_run_requires_one_task_family")
    return next(iter(values))


def normalize_interface(value: Any) -> str:
    """Return the released State-Given/State-Seeking interface name."""
    if not isinstance(value, str):
        raise ValueError(f"unsupported_interface:{value}")
    cleaned = value.strip()
    if cleaned in PUBLIC_INTERFACES:
        return cleaned
    if cleaned not in PUBLIC_INTERFACES:
        raise ValueError(f"unsupported_interface:{value}")
    return cleaned


def interface_slug(value: Any) -> str:
    """Return the filesystem slug used inside the released package."""
    return "State-Given" if normalize_interface(value) == STATE_GIVEN else "State-Seeking"


def implementation_mode(value: Any) -> str:
    """Return the private runner implementation selected by the public view."""
    return "dr" if normalize_interface(value) == STATE_GIVEN else "eia"
