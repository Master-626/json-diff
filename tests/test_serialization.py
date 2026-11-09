"""Exact serialization must never round, quote, or inject decimal values."""

import io
import json
import random
from decimal import Decimal, InvalidOperation, localcontext

import pytest

from json_diff.comparator import InvalidJSON, compare_json, format_value, load_json_stream
from json_diff.serialization import dumps_json


@pytest.mark.parametrize(
    "number", ["1", "-0", "0", "1.00", "1e400", "1e-400", "0.10000000000000001"]
)
def test_decimal_round_trip_preserves_number_and_type(number):
    value = Decimal(number)
    encoded = dumps_json(value)
    assert not encoded.startswith('"')
    decoded = json.loads(encoded, parse_float=Decimal)
    assert type(decoded) is Decimal and decoded == value
    assert decoded.is_signed() == value.is_signed()


@pytest.mark.parametrize(
    "value",
    [
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        float("nan"),
        float("inf"),
    ],
)
def test_non_finite_numbers_are_rejected_everywhere(value):
    with pytest.raises(ValueError):
        dumps_json({"nested": [value]})


@pytest.mark.parametrize("value", [{1: Decimal("1.0")}, {None: 1}, {("x",): 0}])
def test_non_json_object_keys_are_rejected(value):
    with pytest.raises(TypeError, match="keys must be strings"):
        dumps_json(value)


@pytest.mark.parametrize("indent", [-1, 1.5, "  "])
def test_invalid_indentation_is_rejected(indent):
    with pytest.raises(ValueError, match="indent"):
        dumps_json([], indent=indent)


def test_cycles_rejected_but_shared_values_work():
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError, match="Circular"):
        dumps_json(cycle)
    repeated = {"amount": Decimal("1.0")}
    assert dumps_json([repeated, repeated]) == '[{"amount": 1.0}, {"amount": 1.0}]'


def test_disabled_decimal_trap_still_rejects_invalid_exponent():
    with localcontext() as context:
        context.traps[InvalidOperation] = False
        with pytest.raises(InvalidJSON):
            load_json_stream(io.StringIO("1e999999999999999999999"), exact_decimals=True)


def test_lowercase_exponents_in_callers_decimal_context_remain_valid_json():
    with localcontext() as context:
        context.capitals = 0
        for value in (Decimal("1e400"), Decimal("1e-400"), Decimal("0e400")):
            assert json.loads(dumps_json(value), parse_float=Decimal) == value


def test_decimal_subclasses_cannot_inject_json_or_bypass_finite_check():
    class CustomDecimal(Decimal):
        def __str__(self):
            return '0, "injected": true, "other": 0.0'

        def is_finite(self):
            return True

    assert dumps_json({"value": CustomDecimal("1.0")}) == '{"value": 1.0}'
    with pytest.raises(ValueError):
        dumps_json(CustomDecimal("NaN"))


def test_no_placeholder_replacement_can_change_user_strings():
    value = {
        "1E-400": [Decimal("1e-400"), "1E-400", '"1E-400"', "\u0000\n\x1b", "你好", "</script>"]
    }
    text = dumps_json(value)
    assert json.loads(text, parse_float=Decimal) == value
    assert "\\u0000" in text and "\\u001b" in text
    assert format_value(value, None) == text
    assert format_value(Decimal("0.123456789"), 4) == "0.12..."


@pytest.mark.parametrize("indent", [None, 0, 2])
@pytest.mark.parametrize("sort_keys", [False, True])
def test_standard_json_output_matches_existing_encoder(indent, sort_keys):
    randomizer = random.Random(20261109)

    def sample(depth=0):
        if depth > 2 or randomizer.random() < 0.5:
            return randomizer.choice(
                [None, True, False, 0, -1, 1.0, 1e-10, "hello", "你好", "\n", "</script>"]
            )
        if randomizer.random() < 0.5:
            return [sample(depth + 1) for _ in range(randomizer.randrange(4))]
        return {
            key: sample(depth + 1) for key in ["z", "a/b", "~", ""] if randomizer.random() < 0.5
        }

    for _ in range(200):
        value = sample()
        assert dumps_json(value, indent=indent, sort_keys=sort_keys) == json.dumps(
            value, indent=indent, sort_keys=sort_keys, ensure_ascii=True, allow_nan=False
        )


def test_seeded_decimal_round_trips_are_exact_under_small_context():
    randomizer = random.Random(20261109)
    with localcontext() as context:
        context.prec = 3
        for _ in range(200):
            value = Decimal(
                "{}{}e{}".format(
                    randomizer.choice(["", "-"]),
                    randomizer.randrange(10**60),
                    randomizer.randrange(-500, 500),
                )
            )
            original = {"number": [value, "number", 1]}
            decoded = json.loads(dumps_json(original), parse_float=Decimal)
            assert compare_json(original, decoded) == []


def test_maximum_input_depth_serializes_in_difference_report():
    value = load_json_stream(io.StringIO("[" * 200 + "1e-400" + "]" * 200), exact_decimals=True)
    diffs = compare_json({}, value)
    decoded = json.loads(dumps_json(diffs, indent=2), parse_float=Decimal)
    assert compare_json(decoded[0]["new_value"], value) == []


def test_tuple_values_keep_standard_json_array_output():
    assert dumps_json((Decimal("1.0"), 1)) == "[1.0, 1]"
