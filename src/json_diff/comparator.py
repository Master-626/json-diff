"""Deterministic structural comparison of JSON values."""

import json
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, TextIO, Tuple

from .serialization import dumps_json

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


def _decimal(value):
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise InvalidJSON(
            "Number is outside the supported decimal range: {}".format(value)
        ) from error
    # Decimal construction is exact and does not use context precision, but an
    # unsupported exponent can return NaN if the caller disabled its trap.
    if not result.is_finite():
        raise InvalidJSON("Number is outside the supported decimal range: {}".format(value))
    return result


def load_json_stream(stream: TextIO, *, exact_decimals: bool = False) -> Any:
    """Read strict JSON; optionally decode decimal/exponent tokens as Decimal.

    The default retains the legacy binary-float API. Exact mode avoids rounding,
    overflow and underflow within Decimal's supported exponent range. Integer
    tokens remain integers. Duplicate keys and non-finite tokens are rejected.
    A single leading U+FEFF (UTF-8 BOM) is ignored so stdin matches file input.
    """
    text = stream.read()
    if isinstance(text, str) and text.startswith("\ufeff"):
        text = text[1:]
    value = json.loads(
        text,
        object_pairs_hook=_object,
        parse_constant=_constant,
        parse_float=_decimal if exact_decimals else _float,
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


def load_json(file_path: str, *, exact_decimals: bool = False) -> Any:
    """Read a UTF-8 JSON file. A leading UTF-8 BOM is accepted."""
    with open(file_path, "r", encoding="utf-8-sig") as stream:
        return load_json_stream(stream, exact_decimals=exact_decimals)


def _require_string_list(name, value):
    """Return a list of strings. A bare string is not treated as one entry.

    Iterating ``ignore_fields="id"`` would hide the keys ``i`` and ``d``.
    Iterating ``ignore_paths="//"`` would apply the empty-key pointer ``/``
    twice and hide a real change at that key.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        raise ValueError(
            "{} must be a list of strings, not a {}.".format(name, type(value).__name__)
        )
    return list(value)


def _non_finite(value):
    """Raise when a visited value contains NaN or an infinity.

    Ignored subtrees are not scanned. Containers are walked iteratively so a
    self-referential value cannot hang the check.
    """
    stack = [value]
    seen = set()
    while stack:
        current = stack.pop()
        if isinstance(current, float):
            if not math.isfinite(current):
                raise ValueError("Non-finite number is not valid JSON")
        elif isinstance(current, Decimal) and not Decimal.is_finite(current):
            raise ValueError("Non-finite Decimal is not valid JSON")
        elif isinstance(current, (dict, list)):
            marker = id(current)
            if marker in seen:
                continue
            seen.add(marker)
            stack.extend(current.values() if isinstance(current, dict) else current)


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
    ignore_added: bool = False,
) -> List[Dict]:
    """Compare JSON-compatible values (including Decimal) without modifying them.

    Object keys are sorted; arrays are compared by index, including tails.
    ``ignore_fields`` and ``ignore_paths`` must be lists of strings, not a
    single string. ``ignore_fields`` skips exact object-key names at every depth.
    ``ignore_paths`` uses JSON Pointer segments; a whole ``*`` segment matches
    one key or index. Ignoring a container skips its entire subtree.
    ``ignore_added`` omits keys and array elements that exist only in ``obj2``.
    Removals, edits and type changes are still reported. Inserting an array
    element in the middle still changes later indexes.
    Non-finite floats and Decimals that would be compared or reported are
    rejected. Each difference contains path, pointer, type, old_value and new_value.
    The optional legacy ``path`` prefixes display paths only, not pointers.
    """
    ignored_fields = set(_require_string_list("ignore_fields", ignore_fields))
    patterns = _patterns(_require_string_list("ignore_paths", ignore_paths))
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
        _non_finite(old)
        _non_finite(new)
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
                    if ignore_added:
                        continue
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
                    if ignore_added:
                        continue
                    emit(child_display, child_parts, "added", None, new[index])
                elif index >= len(new):
                    emit(child_display, child_parts, "removed", old[index], None)
                else:
                    visit(old[index], new[index], child_display, child_parts)
        else:
            _non_finite(old)
            _non_finite(new)
            if old != new:
                emit(display, parts, "changed", old, new)

    visit(obj1, obj2, path, ())
    return diffs


def format_value(value: Any, max_len: Optional[int] = 50) -> str:
    """Display JSON literals, escaping control characters and preserving null."""
    text = dumps_json(value, sort_keys=True)
    if max_len is not None and len(text) > max_len:
        return text[:max_len] + "..."
    return text
