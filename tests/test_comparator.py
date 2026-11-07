"""Comparison contracts, including cases that caused false-negative gates."""

import copy
import io
import json
import random

import pytest

from json_diff.comparator import (
    InvalidJSON,
    compare_json,
    format_value,
    load_json,
    load_json_stream,
)


@pytest.mark.parametrize("value", [None, True, False, 0, 1.2, "", "你好", [], {}, {"a": [None]}])
def test_equal_values(value):
    assert compare_json(value, copy.deepcopy(value)) == []


@pytest.mark.parametrize("old,new", [(True, 1), (False, 0), (1, 1.0), (None, "null"), ([], {})])
def test_types_are_distinct(old, new):
    assert compare_json(old, new) == [
        {"path": "root", "pointer": "", "type": "changed", "old_value": old, "new_value": new}
    ]


def test_nested_changes_are_deterministic():
    old = {"z": 0, "user": {"name": "Alice"}, "a": None}
    new = {"user": {"name": "Bob"}, "c": True, "a": None}
    diffs = compare_json(old, new)
    assert [(d["pointer"], d["type"]) for d in diffs] == [
        ("/c", "added"),
        ("/user/name", "changed"),
        ("/z", "removed"),
    ]
    assert diffs[1]["path"] == "user.name"
    assert compare_json(dict(reversed(list(old.items()))), new) == diffs


def test_null_and_missing_are_distinguished_by_type():
    diffs = compare_json({"removed": None}, {"added": None})
    assert [d["type"] for d in diffs] == ["added", "removed"]
    assert all(d["old_value"] is None and d["new_value"] is None for d in diffs)


@pytest.mark.parametrize(
    "old,new,kinds",
    [
        ([1], [2, None], ["changed", "added"]),
        ([1, None], [2], ["changed", "removed"]),
        ([], [None, 2], ["added", "added"]),
        ([1, 2], [], ["removed", "removed"]),
    ],
)
def test_array_length_changes_keep_values_and_common_element_changes(old, new, kinds):
    diffs = compare_json(old, new)
    assert [d["type"] for d in diffs] == kinds
    assert [d["pointer"] for d in diffs] == ["/0", "/1"]
    assert all(not isinstance(d["old_value"], str) for d in diffs)


def test_arrays_remain_order_sensitive():
    assert len(compare_json([1, 2], [2, 1])) == 2


@pytest.mark.parametrize(
    "old,new",
    [
        ({"timestamp": 1}, {"timestamp": 2}),
        ({}, {"timestamp": 2}),
        ({"timestamp": 1}, {}),
        ({"user": {"timestamp": 1}}, {"user": {"timestamp": 2}}),
        ({"users": [{"timestamp": 1}]}, {"users": [{"timestamp": 2}]}),
    ],
)
def test_ignore_fields_covers_changed_added_removed_and_nested(old, new):
    assert compare_json(old, new, ignore_fields=["timestamp"]) == []


def test_ignores_use_literal_keys_not_display_path_fragments():
    assert compare_json({"meta.id": 1}, {"meta.id": 2}, ignore_fields=["meta.id"]) == []
    assert len(compare_json({"meta.id": 1}, {"meta.id": 2}, ignore_fields=["id"])) == 1
    assert (
        len(compare_json({"meta": {"id": 1}}, {"meta": {"id": 2}}, ignore_fields=["meta.id"])) == 1
    )


def test_ignore_paths_are_scoped_and_match_one_segment():
    old = {"meta": {"id": 1}, "users": [{"id": 1}, {"id": 2}], "id": 1}
    new = {"meta": {"id": 2}, "users": [{"id": 3}, {"id": 4}], "id": 2}
    diffs = compare_json(old, new, ignore_paths=["/meta/id", "/users/*/id"])
    assert [d["pointer"] for d in diffs] == ["/id"]
    assert compare_json(old, new, ignore_paths=[""]) == []
    assert len(compare_json(old, new, ignore_paths=["/users/*"])) == 2
    assert len(compare_json(old, new, ignore_paths=["/*/id"])) == 3


def test_ignore_paths_apply_before_additions_removals_and_type_changes():
    assert compare_json({"a": 1}, {}, ignore_paths=["/a"]) == []
    assert compare_json({}, {"a": 1}, ignore_paths=["/a"]) == []
    assert compare_json({"a": []}, {"a": {}}, ignore_paths=["/a"]) == []
    assert compare_json([1], [1, 2], ignore_paths=["/1"]) == []
    assert compare_json([1, 2], [1], ignore_paths=["/1"]) == []


@pytest.mark.parametrize("pattern", ["meta/id", "foo", "/bad~", "/bad~2", "/bad~10~"])
def test_invalid_ignore_patterns_fail_loudly(pattern):
    with pytest.raises(ValueError, match="JSON Pointers"):
        compare_json({}, {}, ignore_paths=[pattern])


def test_escaped_pointers_and_display_paths():
    old = {"a.b": {"/": {"~1": {"": 1}}}, "a": {"b": 1}}
    new = {"a.b": {"/": {"~1": {"": 2}}}, "a": {"b": 2}}
    diffs = compare_json(old, new)
    assert [d["pointer"] for d in diffs] == ["/a/b", "/a.b/~1/~01/"]
    assert diffs[1]["path"] == '["a.b"]["/"]["~1"][""]'
    assert len(compare_json(old, new, ignore_paths=["/a.b/~1/~01/"])) == 1


def test_custom_path_prefix_does_not_change_pointer():
    diff = compare_json({"x": 1}, {"x": 2}, path="response")[0]
    assert diff["path"] == "response.x"
    assert diff["pointer"] == "/x"


def test_inputs_are_not_mutated():
    old, new = {"users": [{"id": 1}]}, {"users": [{"id": 2}]}
    snapshot = copy.deepcopy((old, new))
    compare_json(old, new, ignore_paths=["/users/*/id"])
    assert (old, new) == snapshot


@pytest.mark.parametrize(
    "source",
    ['{"a":1,"a":2}', '{"x":{"a":1,"a":2}}', "NaN", "Infinity", "-Infinity", "1e400", "-1e400"],
)
def test_strict_loading_rejects_ambiguous_and_non_finite_inputs(source):
    with pytest.raises(InvalidJSON):
        load_json_stream(io.StringIO(source))


def test_load_json_accepts_utf8_bom(tmp_path):
    path = tmp_path / "bom.json"
    path.write_bytes(b'\xef\xbb\xbf{"a":1}')
    assert load_json(path) == {"a": 1}


@pytest.mark.parametrize("source", ['{"a":', "[1,]", "true false", "", "{invalid}"])
def test_malformed_json_is_rejected(source):
    with pytest.raises(json.JSONDecodeError):
        load_json_stream(io.StringIO(source))


@pytest.mark.parametrize(
    "value,text",
    [(None, "null"), (True, "true"), ("\x1b[31m", '"\\u001b[31m"'), ("a\nb", '"a\\nb"')],
)
def test_format_value_uses_safe_json_literals(value, text):
    assert format_value(value) == text
    assert format_value(value, None) == text


def test_display_truncation_does_not_affect_data():
    value = "x" * 100
    assert format_value(value, 4) == '"xxx...'
    assert json.loads(format_value(value, None)) == value


def _resolve(value, pointer):
    if pointer == "":
        return value
    for part in pointer[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def test_seeded_nested_json_diff_values_match_pointer_targets():
    randomizer = random.Random(2026)

    def sample(depth=0):
        if depth > 2 or randomizer.random() < 0.5:
            return randomizer.choice([None, True, False, 0, 1, 1.0, "<script>", "hello"])
        if randomizer.random() < 0.5:
            return [sample(depth + 1) for _ in range(randomizer.randrange(4))]
        return {
            key: sample(depth + 1) for key in ["a.b", "a/b", "~", ""] if randomizer.random() < 0.5
        }

    for _ in range(200):
        old, new = sample(), sample()
        diffs = compare_json(old, new)
        assert compare_json(old, copy.deepcopy(old)) == []
        assert json.loads(json.dumps(diffs)) == diffs
        assert compare_json(old, new) == diffs
        for diff in diffs:
            if diff["type"] != "added":
                assert _resolve(old, diff["pointer"]) == diff["old_value"]
            if diff["type"] != "removed":
                assert _resolve(new, diff["pointer"]) == diff["new_value"]


def test_standard_finite_floats_load_normally():
    assert load_json_stream(io.StringIO("[1.5, -2e3, 0.0]")) == [1.5, -2000.0, 0.0]


@pytest.mark.parametrize(
    "old,new,kind",
    [
        ({}, {"user": {"id": 1}}, "added"),
        ({"user": {"id": 1}}, {}, "removed"),
        ({"user": {"id": 1}}, {"user": []}, "changed"),
    ],
)
def test_ignoring_child_does_not_hide_whole_parent_changes(old, new, kind):
    diffs = compare_json(old, new, ignore_paths=["/user/id"])
    assert len(diffs) == 1
    assert diffs[0]["pointer"] == "/user"
    assert diffs[0]["type"] == kind


def test_nesting_depth_limit_is_explicit():
    load_json_stream(io.StringIO("[" * 200 + "0" + "]" * 200))
    with pytest.raises(InvalidJSON, match="200 containers"):
        load_json_stream(io.StringIO("[" * 201 + "0" + "]" * 201))
