"""CLI interface for comparing saved API responses and JSON documents."""

import os
import sys
import tempfile
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import __version__
from .comparator import compare_json, format_value, load_json, load_json_stream
from .report import render_report
from .serialization import dumps_json


class InputError(click.ClickException):
    exit_code = 2


def _options(command):
    command = click.option(
        "--exact-decimals",
        is_flag=True,
        help="Compare decimal/exponent numbers exactly instead of using binary floats.",
    )(command)
    command = click.option(
        "--ignore-added",
        is_flag=True,
        help="Do not report keys or array items that exist only in the second file.",
    )(command)
    command = click.option(
        "--ignore-path", multiple=True, help="Ignore a JSON Pointer; * matches one key/index."
    )(command)
    return click.option(
        "--ignore", "-i", multiple=True, help="Ignore this object key at every depth. Repeatable."
    )(command)


def _compare(file1, file2, ignore, ignore_path, exact_decimals, ignore_added):
    if file1 == file2 == "-":
        raise InputError("Only one input may be stdin (-).")
    objects = []
    for filename in (file1, file2):
        try:
            objects.append(
                load_json_stream(sys.stdin, exact_decimals=exact_decimals)
                if filename == "-"
                else load_json(filename, exact_decimals=exact_decimals)
            )
        except (OSError, ValueError, UnicodeError, RecursionError) as error:
            raise InputError("Cannot read {!r}: {}".format(filename, error)) from error
    try:
        return compare_json(
            *objects,
            ignore_fields=list(ignore),
            ignore_paths=list(ignore_path),
            ignore_added=ignore_added,
        )
    except (ValueError, RecursionError) as error:
        raise InputError("Cannot compare inputs: {}".format(error)) from error


@click.group()
@click.version_option(version=__version__)
def main():
    """Compare saved API responses and JSON files. Use - for one stdin input."""


@main.command()
@click.argument("file1", type=click.Path(dir_okay=False, allow_dash=True))
@click.argument("file2", type=click.Path(dir_okay=False, allow_dash=True))
@_options
@click.option("--json-output", is_flag=True, help="Always emit a JSON array, even when equal.")
@click.option("--quiet", "-q", is_flag=True, help="No stdout; report status using the exit code.")
def compare(file1, file2, ignore, ignore_path, exact_decimals, ignore_added, json_output, quiet):
    """Exit 0 when equal, 1 when different, or 2 on input/usage errors."""
    if quiet and json_output:
        raise click.UsageError("--quiet and --json-output cannot be combined.")
    diffs = _compare(file1, file2, ignore, ignore_path, exact_decimals, ignore_added)
    if json_output:
        click.echo(dumps_json(diffs, indent=2))
    elif not quiet:
        console = Console()
        if not diffs:
            console.print("No differences found.", style="green")
        else:
            console.print("Found {} differences:".format(len(diffs)), style="bold red")
            table = Table("Path", "Type", "Old value", "New value")
            for diff in diffs:
                table.add_row(
                    Text(diff["path"]),
                    Text(diff["type"]),
                    Text(
                        "(missing)" if diff["type"] == "added" else format_value(diff["old_value"])
                    ),
                    Text(
                        "(missing)"
                        if diff["type"] == "removed"
                        else format_value(diff["new_value"])
                    ),
                )
            console.print(table)
    raise click.exceptions.Exit(1 if diffs else 0)


@main.command()
@click.argument("file1", type=click.Path(dir_okay=False, allow_dash=True))
@click.argument("file2", type=click.Path(dir_okay=False, allow_dash=True))
@_options
@click.option(
    "--output",
    "-o",
    default="diff_report.html",
    show_default=True,
    type=click.Path(dir_okay=False),
    help="Standalone HTML report path.",
)
@click.option(
    "--fail-on-diff", is_flag=True, help="Exit 1 when different, after saving the report."
)
def report(file1, file2, ignore, ignore_path, exact_decimals, ignore_added, output, fail_on_diff):
    """Save an escaped, offline HTML report. Exit 2 on input/output errors."""
    diffs = _compare(file1, file2, ignore, ignore_path, exact_decimals, ignore_added)
    temporary = None
    try:
        target = Path(output)
        for source in (file1, file2):
            if source != "-" and (
                target.resolve() == Path(source).resolve()
                or (target.exists() and os.path.samefile(target, source))
            ):
                raise InputError("Report output must not overwrite an input file.")
        html = render_report(file1, file2, diffs)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=".json-diff-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = stream.name
            stream.write(html)
        os.replace(temporary, target)
        temporary = None
    except (OSError, ValueError, RecursionError) as error:
        raise InputError("Cannot write report {!r}: {}".format(output, error)) from error
    finally:
        if temporary is not None:
            os.unlink(temporary)
    click.echo("Report saved to {} ({} differences).".format(output, len(diffs)))
    raise click.exceptions.Exit(1 if fail_on_diff and diffs else 0)


if __name__ == "__main__":
    main()
