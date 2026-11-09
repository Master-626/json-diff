"""Exact-decimal mode must preserve numbers across comparison and output."""

import io
import json
from decimal import Decimal, localcontext
from html import unescape

import pytest
from click.testing import CliRunner

from json_diff.cli import main
from json_diff.comparator import (
    InvalidJSON,
    compare_json,
    format_value,
    load_json,
    load_json_stream,
)


def load(text, exact=True):
    return load_json_stream(io.StringIO(text), exact_decimals=exact)


@pytest.mark.parametrize(
    "old,new",
    [
        ("0.10000000000000000", "0.10000000000000001"),
        ("1e-400", "0.0"),
        ("9007199254740992.0", "9007199254740993.0"),
    ],
)
def test_exact_mode_finds_differences_lost_by_binary_float(old, new):
    assert compare_json(load(old, False), load(new, False)) == []
    assert len(compare_json(load(old), load(new))) == 1


@pytest.mark.parametrize("old,new", [("1.0", "1e0"), ("1.2300", "1.23"), ("-0.0", "0e5")])
def test_exact_mode_compares_values_not_spelling(old, new):
    assert compare_json(load(old), load(new)) == []


@pytest.mark.parametrize("old,new", [("1", "1.0"), ("1", "1e0"), ("true", "1.0")])
def test_exact_mode_preserves_integer_decimal_and_boolean_types(old, new):
    assert len(compare_json(load(old), load(new))) == 1


def test_default_api_keeps_float_and_exact_api_returns_decimal(tmp_path):
    source = "[1, 0.10000000000000001, 1e400, 1e-400]"
    path = tmp_path / "numbers.json"
    path.write_text("\ufeff" + source, encoding="utf-8")
    numbers = load_json(path, exact_decimals=True)
    assert type(numbers[0]) is int
    assert all(type(n) is Decimal for n in numbers[1:])
    assert numbers == [1, Decimal("0.10000000000000001"), Decimal("1e400"), Decimal("1e-400")]
    assert type(load_json_stream(io.StringIO("1.0"))) is float
    # Do not silently convert caller-supplied floats, whose original digits are lost.
    assert len(compare_json(1.0, Decimal("1.0"))) == 1


def test_decimal_loading_and_formatting_do_not_use_context_precision():
    source = "0.123456789012345678901234567890123456789"
    with localcontext() as context:
        context.prec = 2
        context.Emax = 2
        context.Emin = -2
        assert format_value(load(source), None) == source
        assert load("1e400") == Decimal("1e400")
        assert load("1e-400") == Decimal("1e-400")


@pytest.mark.parametrize(
    "source", ["NaN", "Infinity", "-Infinity", '{"a":1,"a":2}', "1e999999999999999999999"]
)
def test_exact_mode_still_rejects_ambiguous_or_unrepresentable_input(source):
    with pytest.raises(InvalidJSON):
        load(source)


@pytest.mark.parametrize("source", ["[1,]", "01.0", "+1.0", ".1", "1.", "1e"])
def test_exact_mode_still_requires_json_number_syntax(source):
    with pytest.raises(json.JSONDecodeError):
        load(source)


def test_exact_mode_keeps_depth_limit():
    load("[" * 200 + "1e-400" + "]" * 200)
    with pytest.raises(InvalidJSON, match="200 containers"):
        load("[" * 201 + "1e-400" + "]" * 201)


@pytest.mark.parametrize("command", ["compare", "report"])
def test_exact_cli_json_and_html_keep_full_nested_numbers(tmp_path, command):
    old, new, report = (tmp_path / name for name in ("old.json", "new.json", "report.html"))
    old.write_text('{"value": 0.10000000000000000, "tiny": 0.0}', encoding="utf-8")
    new.write_text(
        '{"value": 0.10000000000000001, "tiny": 1e-400, "added": [1e400, 1e0, "<script>"]}',
        encoding="utf-8",
    )
    args = [command, str(old), str(new), "--exact-decimals"]
    args += ["--json-output"] if command == "compare" else ["-o", str(report), "--fail-on-diff"]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 1, result.output
    if command == "compare":
        diffs = json.loads(result.output, parse_float=Decimal)
        assert diffs[0]["new_value"] == [Decimal("1e400"), Decimal("1"), "<script>"]
        assert type(diffs[0]["new_value"][1]) is Decimal
        assert diffs[1]["new_value"] == Decimal("1e-400")
        assert diffs[2]["new_value"] == Decimal("0.10000000000000001")
    else:
        html = report.read_text(encoding="utf-8")
        assert "<script>" not in html and "&lt;script&gt;" in html
        assert "0.10000000000000001" in html
        assert "1E-400" in html and "1E+400" in html
        assert '[1E+400, 1.0, "<script>"]' in unescape(html)


@pytest.mark.parametrize("command", ["compare", "report"])
def test_exact_cli_supports_stdin_and_ignores(tmp_path, command):
    path, report = tmp_path / "input.json", tmp_path / "report.html"
    path.write_text('{"ignored":1e-400,"meta":{"id":1.1},"value":1e0}', encoding="utf-8")
    args = [
        command,
        str(path),
        "-",
        "--exact-decimals",
        "--ignore",
        "ignored",
        "--ignore-path",
        "/meta/id",
    ]
    args += ["--json-output"] if command == "compare" else ["-o", str(report), "--fail-on-diff"]
    result = CliRunner().invoke(
        main, args, input='{"ignored":2e-400,"meta":{"id":2.2},"value":1.0}'
    )
    assert result.exit_code == 0, result.output
    if command == "compare":
        assert json.loads(result.output) == []
    else:
        assert "No differences found." in report.read_text(encoding="utf-8")


def test_exact_cli_terminal_and_quiet(tmp_path):
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text("0.0", encoding="utf-8")
    new.write_text("1e-400", encoding="utf-8")
    args = ["compare", str(old), str(new), "--exact-decimals"]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 1 and "1E-400" in result.output
    result = CliRunner().invoke(main, args + ["--quiet"])
    assert result.exit_code == 1 and result.output == ""


@pytest.mark.parametrize("command", ["compare", "report"])
def test_exact_cli_bad_exponent_is_clean_error(tmp_path, command):
    path, report = tmp_path / "input.json", tmp_path / "report.html"
    path.write_text("1e999999999999999999999", encoding="utf-8")
    report.write_text("keep", encoding="utf-8")
    args = [command, str(path), str(path), "--exact-decimals"]
    if command == "report":
        args += ["-o", str(report)]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 2 and "Cannot read" in result.output
    assert "Traceback" not in result.output
    assert report.read_text(encoding="utf-8") == "keep"
