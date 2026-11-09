"""End-to-end CLI output, status codes and report safety contracts."""

import json
import os
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest
from click.testing import CliRunner

from json_diff.cli import main
from json_diff.report import render_report


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def inputs(tmp_path):
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text('{"meta":{"request_id":"a"},"value":1}', encoding="utf-8")
    new.write_text('{"meta":{"request_id":"b"},"value":2}', encoding="utf-8")
    return str(old), str(new)


def test_equal_json_output_is_always_parseable(runner, inputs):
    result = runner.invoke(main, ["compare", inputs[0], inputs[0], "--json-output"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []


def test_changed_json_output_has_no_decoration_or_truncation(runner, inputs):
    result = runner.invoke(main, ["compare", *inputs, "--json-output"])
    assert result.exit_code == 1
    assert len(json.loads(result.output)) == 2
    assert "\x1b" not in result.output


def test_comparison_options_are_consistent(runner, inputs):
    result = runner.invoke(
        main,
        [
            "compare",
            *inputs,
            "--ignore-path",
            "/meta/request_id",
            "--ignore",
            "value",
            "--json-output",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == []


@pytest.mark.parametrize("equal,expected", [(True, 0), (False, 1)])
def test_quiet_outputs_nothing(runner, inputs, equal, expected):
    result = runner.invoke(main, ["compare", inputs[0], inputs[0] if equal else inputs[1], "-q"])
    assert result.exit_code == expected
    assert result.output == ""


def test_conflicting_output_flags_are_usage_error(runner, inputs):
    result = runner.invoke(main, ["compare", *inputs, "--quiet", "--json-output"])
    assert result.exit_code == 2
    assert "cannot be combined" in result.output


@pytest.mark.parametrize("argument", ["bad", "/bad~2"])
def test_invalid_ignore_path_is_error_not_diff(runner, inputs, argument):
    result = runner.invoke(main, ["compare", *inputs, "--ignore-path", argument])
    assert result.exit_code == 2
    assert "JSON Pointers" in result.output


@pytest.mark.parametrize("source", ['{"a":', "NaN", '{"a":1,"a":2}', "1e400", ""])
def test_input_errors_do_not_print_tracebacks(runner, inputs, tmp_path, source):
    path = tmp_path / "bad.json"
    path.write_text(source)
    result = runner.invoke(main, ["compare", str(path), inputs[1], "--json-output"])
    assert result.exit_code == 2
    assert "Cannot read" in result.output
    assert "Traceback" not in result.output


def test_invalid_utf8_is_friendly_error(runner, inputs, tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b'"\xff"')
    result = runner.invoke(main, ["compare", str(path), inputs[1]])
    assert result.exit_code == 2
    assert "Cannot read" in result.output


def test_missing_file_is_error(runner, inputs, tmp_path):
    result = runner.invoke(main, ["compare", str(tmp_path / "missing.json"), inputs[1]])
    assert result.exit_code == 2


@pytest.mark.parametrize("left", [True, False])
def test_stdin_can_be_either_input(runner, inputs, left):
    arguments = ["-", inputs[0]] if left else [inputs[0], "-"]
    result = runner.invoke(
        main, ["compare", *arguments, "--json-output"], input=Path(inputs[0]).read_text()
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == []


def test_two_stdin_inputs_rejected(runner):
    result = runner.invoke(main, ["compare", "-", "-"], input="{}")
    assert result.exit_code == 2
    assert "Only one input" in result.output


def test_terminal_values_are_not_rich_markup(runner, tmp_path):
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text("{}")
    new.write_text(json.dumps({"[bold]": "[red]hello[/red]"}))
    result = runner.invoke(main, ["compare", str(old), str(new)], terminal_width=140)
    assert result.exit_code == 1
    assert "[red]hello[/red]" in result.output
    assert "[bold]" in result.output


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, data):
        self.text.append(data)


def test_report_escapes_keys_values_and_filenames(runner, tmp_path):
    # Ampersands need HTML escaping and are valid in Windows and POSIX filenames.
    old, new = tmp_path / "old&name.json", tmp_path / "new.json"
    old.write_text("{}")
    payload = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    new.write_text(json.dumps({payload: payload, "nil": None, "long": "x" * 300}))
    target = tmp_path / "report.html"
    result = runner.invoke(main, ["report", str(old), str(new), "-o", str(target)])
    assert result.exit_code == 0, result.output
    html = target.read_text(encoding="utf-8")
    assert "font-family:" in html
    assert "Content-Security-Policy" in html
    assert "old&amp;name.json" in html
    assert "<script>" not in html and "<img" not in html and "<b>" not in html
    parser = Tags()
    parser.feed(html)
    assert "script" not in parser.tags and "img" not in parser.tags and "b" not in parser.tags
    assert any(json.dumps(payload) in text for text in parser.text)
    assert "x" * 300 in html
    assert "(missing)" in html and "null" in html


def test_report_escapes_markup_in_arbitrary_display_names():
    # Display names need not be filesystem paths; test markup on every platform.
    html = render_report("<b>old.json", '<script>alert("x")</script>', [])
    assert "<b>" not in html and "<script>" not in html
    assert "&lt;b&gt;old.json" in html and "&lt;script&gt;" in html


@pytest.mark.parametrize("fail_on_diff,expected", [(False, 0), (True, 1)])
def test_report_exit_semantics(runner, inputs, tmp_path, fail_on_diff, expected):
    target = tmp_path / "report.html"
    arguments = ["report", *inputs, "-o", str(target)] + (
        ["--fail-on-diff"] if fail_on_diff else []
    )
    result = runner.invoke(main, arguments)
    assert result.exit_code == expected
    assert target.is_file()


def test_report_supports_same_ignore_options(runner, inputs, tmp_path):
    target = tmp_path / "report.html"
    result = runner.invoke(
        main,
        [
            "report",
            *inputs,
            "-o",
            str(target),
            "--fail-on-diff",
            "--ignore-path",
            "/meta/request_id",
            "-i",
            "value",
        ],
    )
    assert result.exit_code == 0
    assert "No differences found." in target.read_text()


def test_report_does_not_overwrite_input(runner, inputs):
    original = Path(inputs[0]).read_bytes()
    result = runner.invoke(main, ["report", *inputs, "-o", inputs[0]])
    assert result.exit_code == 2
    assert "must not overwrite" in result.output
    assert Path(inputs[0]).read_bytes() == original


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_report_does_not_overwrite_input_alias(runner, inputs, tmp_path, kind):
    target = tmp_path / "alias.html"
    try:
        (os.symlink if kind == "symlink" else os.link)(inputs[0], target)
    except (OSError, NotImplementedError):
        pytest.skip("Filesystem does not support links")
    result = runner.invoke(main, ["report", *inputs, "-o", str(target)])
    assert result.exit_code == 2
    assert "must not overwrite" in result.output


def test_report_output_error_is_friendly(runner, inputs, tmp_path):
    result = runner.invoke(
        main, ["report", *inputs, "-o", str(tmp_path / "missing" / "report.html")]
    )
    assert result.exit_code == 2
    assert "Cannot write report" in result.output
    assert "Traceback" not in result.output


def test_report_failed_replace_keeps_existing_file_and_cleans_temp(
    runner, inputs, tmp_path, monkeypatch
):
    target = tmp_path / "report.html"
    target.write_text("existing report")

    def fail_replace(*args):
        raise OSError("simulated write failure")

    monkeypatch.setattr("json_diff.cli.os.replace", fail_replace)
    result = runner.invoke(main, ["report", *inputs, "-o", str(target)])
    assert result.exit_code == 2
    assert target.read_text() == "existing report"
    assert not list(tmp_path.glob(".json-diff-*.tmp"))


def test_installed_cli_stdout_and_stderr_contract(inputs, tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "json_diff.cli", "compare", *inputs, "--json-output"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert len(json.loads(result.stdout)) == 2
    assert result.stderr == ""
    error = subprocess.run(
        [sys.executable, "-m", "json_diff.cli", "compare", inputs[0], str(tmp_path / "missing")],
        capture_output=True,
        text=True,
    )
    assert error.returncode == 2
    assert error.stdout == ""
    assert "Cannot read" in error.stderr


def test_help_and_version(runner):
    assert runner.invoke(main, ["--help"]).exit_code == 0
    assert runner.invoke(main, ["--version"]).exit_code == 0


def test_equal_human_output(runner, inputs):
    result = runner.invoke(main, ["compare", inputs[0], inputs[0]])
    assert result.exit_code == 0
    assert "No differences found." in result.output


def test_report_bad_input_leaves_existing_output_intact(runner, inputs, tmp_path):
    target, bad = tmp_path / "report.html", tmp_path / "bad.json"
    target.write_text("original")
    bad.write_text('{"duplicate":1,"duplicate":2}')
    result = runner.invoke(main, ["report", inputs[0], str(bad), "-o", str(target)])
    assert result.exit_code == 2
    assert target.read_text() == "original"


def test_deeply_nested_input_is_friendly_error(runner, inputs, tmp_path):
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 2000 + "0" + "]" * 2000)
    result = runner.invoke(main, ["compare", inputs[0], str(deep), "--json-output"])
    assert result.exit_code == 2
    assert "Cannot read" in result.output
    assert "Traceback" not in result.output


def test_documented_examples_are_executable(runner):
    root = Path(__file__).resolve().parents[1]
    expected = str(root / "examples" / "expected.json")
    flags = [
        "--ignore-path",
        "/meta/request_id",
        "--ignore-path",
        "/meta/generated_at",
        "--json-output",
    ]
    changed = runner.invoke(
        main, ["compare", expected, str(root / "examples" / "actual.json"), *flags]
    )
    assert changed.exit_code == 1
    assert [(d["pointer"], d["type"]) for d in json.loads(changed.output)] == [
        ("/users/0/role", "changed"),
        ("/users/1", "added"),
    ]
    equal = runner.invoke(
        main, ["compare", expected, str(root / "examples" / "equivalent.json"), *flags]
    )
    assert equal.exit_code == 0
    assert json.loads(equal.output) == []
