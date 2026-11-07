"""Deterministic structural comparison of JSON values."""

import json
import math
import re
from typing import Any, Dict, Iterable, List, Optional, TextIO, Tuple

MAX_DEPTH = 200


class InvalidJSON(ValueError):
    """Input would be lossy or is not standard JSON."""


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidJSON("Duplicate object key: {!r}".format(key))
        result[key] = value
    return result


def _constant(value):
    raise InvalidJSON("Non-finite number is not valid JSON: {}".format(value))


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        raise InvalidJSON("Number is outside the finite float range: {}".format(value))
    return result


def load_json_stream(stream: TextIO) -> Any:
    """Read strict JSON, rejecting duplicate keys and non-finite numbers."""
    value = json.load(
        stream, object_pairs_hook=_object, parse_constant=_constant, parse_float=_float
    )
    # Bound traversal/serialization depth even if the platform decoder accepts
    # deeper input. Walking iteratively avoids spending another recursion stack.
    stack = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if isinstance(current, (dict, list)):
            if depth > MAX_DEPTH:
                raise InvalidJSON("Document nesting exceeds {} containers.".format(MAX_DEPTH))
            children = current.values() if isinstance(current, dict) else current
            stack.extend(
                (child, depth + 1) for child in children if isinstance(child, (dict, list))
            )
    return value


def load_json(file_path: str) -> Any:
    """Read a UTF-8 JSON file. A leading UTF-8 BOM is accepted."""
    with open(file_path, "r", encoding="utf-8-sig") as stream:
        return load_json_stream(stream)


def _patterns(paths: Iterable[str]) -> List[Tuple[str, ...]]:
    result = []
    for path in paths:
        if path == "":
            result.append(())
            continue
        if not path.startswith("/") or re.search(r"~(?![01])", path):
            raise ValueError(
                "Ignore paths must be JSON Pointers (for example /meta/request_id); "
                "escape '~' as '~0' and '/' as '~1'."
            )
        result.append(
            tuple(part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/"))
        )
    return result


def _pointer(parts: Tuple[str, ...]) -> str:
    return "".join("/" + part.replace("~", "~0").replace("/", "~1") for part in parts)


def _child_path(path: str, key: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", key):
        return "{}.{}".format(path, key) if path else key
    return "{}[{}]".format(path, json.dumps(key, ensure_ascii=True))


def compare_json(
    obj1: Any,
    obj2: Any,
    path: str = "",
    ignore_fields: Optional[List[str]] = None,
    *,
    ignore_paths: Optional[List[str]] = None,
) -> List[Dict]:
    """Compare JSON-compatible values without modifying them.

    Object keys are sorted; arrays are compared by index, including tails.
    ``ignore_fields`` skips exact object-key names at every depth.
    ``ignore_paths`` uses JSON Pointer segments; a whole ``*`` segment matches
    one key or index. Ignoring a container skips its entire subtree.
    Each difference contains path, pointer, type, old_value and new_value.
    The optional legacy ``path`` prefixes display paths only, not pointers.
    """
    ignored_fields = set(ignore_fields or [])
    patterns = _patterns(ignore_paths or [])
    diffs = []

    def ignored(parts):
        return any(
            len(parts) == len(pattern)
            and all(
                expected == "*" or actual == expected for actual, expected in zip(parts, pattern)
            )
            for pattern in patterns
        )

    def emit(display, parts, kind, old, new):
        diffs.append(
            {
                "path": display or "root",
                "pointer": _pointer(parts),
                "type": kind,
                "old_value": old,
                "new_value": new,
            }
        )

    def visit(old, new, display, parts):
        if ignored(parts):
            return
        # Keep bool distinct from int and preserve the original type-strict API.
        if type(old) is not type(new):
            emit(display, parts, "changed", old, new)
        elif isinstance(old, dict):
            for key in sorted(old.keys() | new.keys()):
                child_parts = parts + (key,)
                if key in ignored_fields or ignored(child_parts):
                    continue
                child_display = _child_path(display, key)
                if key not in old:
                    emit(child_display, child_parts, "added", None, new[key])
                elif key not in new:
                    emit(child_display, child_parts, "removed", old[key], None)
                else:
                    visit(old[key], new[key], child_display, child_parts)
        elif isinstance(old, list):
            for index in range(max(len(old), len(new))):
                child_parts = parts + (str(index),)
                if ignored(child_parts):
                    continue
                child_display = "{}[{}]".format(display, index)
                if index >= len(old):
                    emit(child_display, child_parts, "added", None, new[index])
                elif index >= len(new):
                    emit(child_display, child_parts, "removed", old[index], None)
                else:
                    visit(old[index], new[index], child_display, child_parts)
        elif old != new:
            emit(display, parts, "changed", old, new)

    visit(obj1, obj2, path, ())
    return diffs


def format_value(value: Any, max_len: Optional[int] = 50) -> str:
    """Display JSON literals, escaping control characters and preserving null."""
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False)
    if max_len is not None and len(text) > max_len:
        return text[:max_len] + "..."
    return text
