"""CLI interface for json-diff."""

import sys
import click
from rich.console import Console
from rich.table import Table

from .comparator import compare_json, load_json, format_value

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """JSON Diff - Compare JSON files with colored output."""
    pass


@main.command()
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", type=click.Path(exists=True))
@click.option("--ignore", "-i", multiple=True, help="Fields to ignore (can be used multiple times)")
@click.option("--json-output", is_flag=True, help="Output diff as JSON")
def compare(file1, file2, ignore, json_output):
    """Compare two JSON files and show differences."""
    obj1 = load_json(file1)
    obj2 = load_json(file2)

    diffs = compare_json(obj1, obj2, ignore_fields=list(ignore))

    if not diffs:
        console.print("[bold green]✓ No differences found![/bold green]")
        sys.exit(0)

    if json_output:
        import json
        print(json.dumps(diffs, indent=2))
    else:
        console.print(f"[bold red]✗ Found {len(diffs)} differences:[/bold red]\n")

        table = Table(show_header=True)
        table.add_column("Path", style="cyan")
        table.add_column("Type", style="yellow")
        table.add_column("Old Value", style="red")
        table.add_column("New Value", style="green")

        for diff in diffs:
            type_colors = {
                "added": "green",
                "removed": "red",
                "changed": "yellow",
            }
            type_color = type_colors.get(diff["type"], "white")

            table.add_row(
                diff["path"],
                f"[{type_color}]{diff['type']}[/{type_color}]",
                format_value(diff["old_value"]),
                format_value(diff["new_value"]),
            )

        console.print(table)

    # Exit code 1 if differences found (for CI/CD)
    sys.exit(1)


@main.command()
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", type=click.Path(exists=True))
@click.option("--output", "-o", default="diff_report.html", help="Output HTML file")
def report(file1, file2, output):
    """Generate an HTML diff report."""
    obj1 = load_json(file1)
    obj2 = load_json(file2)

    diffs = compare_json(obj1, obj2)

    html = """<!DOCTYPE html>
<html>
<head>
    <title>JSON Diff Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .added { background-color: #d4edda; }
        .removed { background-color: #f8d7da; }
        .changed { background-color: #fff3cd; }
    </style>
</head>
<body>
    <h1>JSON Diff Report</h1>
    <p><strong>File 1:</strong> {file1}</p>
    <p><strong>File 2:</strong> {file2}</p>
    <p><strong>Total differences:</strong> {count}</p>
    <table>
        <tr><th>Path</th><th>Type</th><th>Old Value</th><th>New Value</th></tr>
        {rows}
    </table>
</body>
</html>""".format(
        file1=file1,
        file2=file2,
        count=len(diffs),
        rows="\n".join(
            f'<tr class="{d["type"]}"><td>{d["path"]}</td><td>{d["type"]}</td>'
            f'<td>{d["old_value"]}</td><td>{d["new_value"]}</td></tr>'
            for d in diffs
        )
    )

    with open(output, "w", encoding="utf-8") as f:
        f.write(html)

    console.print(f"[bold green]✓ Report saved to {output}[/bold green]")


if __name__ == "__main__":
    main()
