from __future__ import annotations

from pathlib import Path
from typing import Any


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load the small YAML subset used by Lab Radar config files."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        text = raw.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]
        if text.startswith("- "):
            value = _parse_scalar(text[2:].strip())
            if not isinstance(parent, list):
                raise ValueError(f"List item has no list parent: {raw}")
            parent.append(value)
            continue

        if ":" not in text:
            raise ValueError(f"Invalid config line: {raw}")
        key, raw_value = text.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        if raw_value:
            parent[key] = _parse_scalar(raw_value)
            continue

        child = _next_container(lines, raw)
        parent[key] = child
        stack.append((indent, child))

    return root


def _next_container(lines: list[str], current: str) -> dict[str, Any] | list[Any]:
    current_index = lines.index(current)
    current_indent = len(current) - len(current.lstrip(" "))
    for later in lines[current_index + 1 :]:
        if not later.strip() or later.lstrip().startswith("#"):
            continue
        later_indent = len(later) - len(later.lstrip(" "))
        if later_indent <= current_indent:
            return {}
        return [] if later.strip().startswith("- ") else {}
    return {}


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value
