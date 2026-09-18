"""Tests for JSON comparator."""

from json_diff.comparator import compare_json


def test_no_differences():
    obj1 = {"name": "Alice", "age": 30}
    obj2 = {"name": "Alice", "age": 30}
    assert compare_json(obj1, obj2) == []


def test_simple_change():
    obj1 = {"name": "Alice", "age": 30}
    obj2 = {"name": "Bob", "age": 30}
    diffs = compare_json(obj1, obj2)
    assert len(diffs) == 1
    assert diffs[0]["path"] == "name"
    assert diffs[0]["type"] == "changed"


def test_added_field():
    obj1 = {"name": "Alice"}
    obj2 = {"name": "Alice", "age": 30}
    diffs = compare_json(obj1, obj2)
    assert len(diffs) == 1
    assert diffs[0]["type"] == "added"
    assert diffs[0]["path"] == "age"


def test_removed_field():
    obj1 = {"name": "Alice", "age": 30}
    obj2 = {"name": "Alice"}
    diffs = compare_json(obj1, obj2)
    assert len(diffs) == 1
    assert diffs[0]["type"] == "removed"


def test_nested_objects():
    obj1 = {"user": {"name": "Alice", "address": {"city": "NYC"}}}
    obj2 = {"user": {"name": "Alice", "address": {"city": "LA"}}}
    diffs = compare_json(obj1, obj2)
    assert len(diffs) == 1
    assert diffs[0]["path"] == "user.address.city"


def test_ignore_fields():
    obj1 = {"name": "Alice", "timestamp": "2024-01-01"}
    obj2 = {"name": "Alice", "timestamp": "2024-01-02"}
    diffs = compare_json(obj1, obj2, ignore_fields=["timestamp"])
    assert diffs == []
