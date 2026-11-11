"""Standalone HTML reports. Every value from the input is escaped as text."""

from html import escape

from .comparator import format_value


def _text(value):
    """Escape markup and keep the report encodable as UTF-8.

    JSON keys may contain lone surrogates (``\\uD800``). Those characters cannot
    be written as UTF-8, so spell them as ``\\uXXXX`` before HTML escaping.
    Ordinary non-ASCII text is left unchanged.
    """
    safe = str(value).encode("utf-8", "backslashreplace").decode("utf-8")
    return escape(safe)


def render_report(file1, file2, diffs):
    rows = []
    for diff in diffs:
        cells = [
            diff["pointer"] or "(root)",
            diff["type"],
            "(missing)" if diff["type"] == "added" else format_value(diff["old_value"], None),
            "(missing)" if diff["type"] == "removed" else format_value(diff["new_value"], None),
        ]
        rows.append(
            "<tr>"
            + "".join("<td><pre>{}</pre></td>".format(_text(cell)) for cell in cells)
            + "</tr>"
        )
    # Join fixed markup rather than interpreting CSS braces as format fields.
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>JSON Diff Report</title>
<style>
body { font-family: system-ui, sans-serif; margin: 2rem; color: #182230; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #cbd5e1; padding: .75rem; text-align: left; vertical-align: top; }
th { background: #f1f5f9; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; }
</style>
</head>
<body>
<h1>JSON Diff Report</h1>
""" + "\n".join(
        [
            "<p><strong>Expected:</strong> {}</p>".format(_text(file1)),
            "<p><strong>Actual:</strong> {}</p>".format(_text(file2)),
            "<p><strong>Total differences:</strong> {}</p>".format(len(diffs)),
            '<table><thead><tr><th scope="col">JSON Pointer</th><th scope="col">Type</th>'
            '<th scope="col">Old value</th><th scope="col">New value</th></tr></thead><tbody>',
            "\n".join(rows),
            "</tbody></table>",
            "<p>No differences found.</p>" if not diffs else "",
            "</body></html>\n",
        ]
    )
