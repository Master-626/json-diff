"""Core JSON comparison logic."""

import json
from typing import Any, Dict, List, Tuple


def load_json(file_path: str) -> Any:
    """Load JSON from a file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_json(
    obj1: Any,
    obj2: Any,
    path: str = "",
    ignore_fields: List[str] = None,
) -> List[Dict]:
    """Compare two JSON objects recursively and return differences.
    
    Returns list of diffs: {path, type, old_value, new_value}
    type: "added", "removed", "changed"
    """
    ignore_fields = ignore_fields or []
    diffs = []

    # Check if current path should be ignored
    current_key = path.split(".")[-1] if path else ""
    if current_key in ignore_fields:
        return diffs

    if type(obj1) != type(obj2):
        diffs.append({
            "path": path or "root",
            "type": "changed",
            "old_value": obj1,
            "new_value": obj2,
        })
        return diffs

    if isinstance(obj1, dict):
        all_keys = set(obj1.keys()) | set(obj2.keys())
        for key in sorted(all_keys):
            new_path = f"{path}.{key}" if path else key
            if key not in obj1:
                diffs.append({
                    "path": new_path,
                    "type": "added",
                    "old_value": None,
                    "new_value": obj2[key],
                })
            elif key not in obj2:
                diffs.append({
                    "path": new_path,
                    "type": "removed",
                    "old_value": obj1[key],
                    "new_value": None,
                })
            else:
                diffs.extend(compare_json(obj1[key], obj2[key], new_path, ignore_fields))

    elif isinstance(obj1, list):
        if len(obj1) != len(obj2):
            diffs.append({
                "path": path or "root",
                "type": "changed",
                "old_value": f"list length {len(obj1)}",
                "new_value": f"list length {len(obj2)}",
            })
            return diffs
        for i, (item1, item2) in enumerate(zip(obj1, obj2)):
            new_path = f"{path}[{i}]"
            diffs.extend(compare_json(item1, item2, new_path, ignore_fields))

    else:
        if obj1 != obj2:
            diffs.append({
                "path": path or "root",
                "type": "changed",
                "old_value": obj1,
                "new_value": obj2,
            })

    return diffs


def format_value(value: Any, max_len: int = 50) -> str:
    """Format a value for display."""
    if isinstance(value, (dict, list)):
        s = json.dumps(value, indent=2)
    else:
        s = str(value)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s
