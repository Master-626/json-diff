"""JSON serialization that preserves finite Decimal values as JSON numbers."""

import json
from decimal import Decimal
from typing import Any, Optional


def dumps_json(value: Any, *, indent: Optional[int] = None, sort_keys: bool = False) -> str:
    """Serialize JSON values plus Decimal, without a float or string conversion.

    Keys must be strings. Decimal values always retain a decimal point or
    exponent so parsing the report preserves the integer/decimal distinction.
    Non-finite values and circular containers are rejected. Strings are escaped
    by the standard JSON encoder, including control characters and non-ASCII.
    """
    if indent is not None and (not isinstance(indent, int) or indent < 0):
        raise ValueError("indent must be a non-negative integer or None")
    active = set()

    def encode(current, depth):
        if isinstance(current, Decimal):
            if not Decimal.is_finite(current):
                raise ValueError("Non-finite Decimal is not valid JSON")
            number = Decimal.__str__(current)
            return number if "." in number or "e" in number.lower() else number + ".0"
        if not isinstance(current, (dict, list, tuple)):
            return json.dumps(current, ensure_ascii=True, allow_nan=False)
        identity = id(current)
        if identity in active:
            raise ValueError("Circular reference detected")
        active.add(identity)
        try:
            entries = []
            if isinstance(current, dict):
                if any(not isinstance(key, str) for key in current):
                    raise TypeError("JSON object keys must be strings")
                keys = sorted(current) if sort_keys else current
                for key in keys:
                    entries.append(
                        json.dumps(key, ensure_ascii=True) + ": " + encode(current[key], depth + 1)
                    )
                opening, closing = "{", "}"
            else:
                for child in current:
                    entries.append(encode(child, depth + 1))
                opening, closing = "[", "]"
            if not entries:
                return opening + closing
            if indent is None:
                return opening + ", ".join(entries) + closing
            prefix = " " * (indent * (depth + 1))
            return (
                opening
                + "\n"
                + prefix
                + (",\n" + prefix).join(entries)
                + "\n"
                + " " * (indent * depth)
                + closing
            )
        finally:
            active.remove(identity)

    return encode(value, 0)
