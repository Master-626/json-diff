"""Render the real bundled-example CLI output as a README SVG.

Run from a checkout with this project installed: python docs/generate_demo.py
No screenshot, network request or sample-output substitution is involved.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
ARGS = [
    "compare",
    "examples/expected.json",
    "examples/actual.json",
    "--ignore-path",
    "/meta/request_id",
    "--ignore-path",
    "/meta/generated_at",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs")
    output = parser.parse_args().output_dir
    env = dict(os.environ, COLUMNS="100", NO_COLOR="1", TERM="dumb")
    env.pop("FORCE_COLOR", None)
    result = subprocess.run(
        [sys.executable, "-m", "json_diff.cli", *ARGS],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    data = subprocess.run(
        [sys.executable, "-m", "json_diff.cli", *ARGS, "--json-output"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 1 or data.returncode != 1 or result.stderr or data.stderr:
        raise RuntimeError("Example did not return the expected diff status: {}".format(result))
    expected = [("/users/0/role", "changed"), ("/users/1", "added")]
    if [(item["pointer"], item["type"]) for item in json.loads(data.stdout)] != expected:
        raise RuntimeError(
            "Bundled example changed; review the README narrative before regenerating."
        )
    lines = [
        "$ json-diff compare examples/expected.json examples/actual.json \\",
        "    --ignore-path /meta/request_id --ignore-path /meta/generated_at",
        "",
        *result.stdout.rstrip().splitlines(),
        "",
        "Exit code: {} (differences found)".format(result.returncode),
    ]
    width, height = max(760, 56 + 9 * max(map(len, lines))), 104 + 23 * len(lines)
    body = []
    for index, line in enumerate(lines):
        color = "#7dd3fc" if index < 2 else "#e2e8f0"
        if index == len(lines) - 1:
            color = "#fcd34d"
        body.append(
            '<text x="28" y="{}" fill="{}">{}</text>'.format(88 + index * 23, color, escape(line))
        )
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">JSON Diff: two changes in a saved API response</title>
<desc id="desc">Actual CLI output from the bundled examples: one role changed and one user added. Volatile metadata is ignored. Exit status is 1.</desc>
<rect width="{width}" height="{height}" rx="16" fill="#0f172a"/>
<text x="28" y="36" fill="#94a3b8" font-family="sans-serif" font-size="16">JSON DIFF · SAVED RESPONSE CHECK</text>
<path d="M28 53 H{right}" stroke="#334155"/>
<g font-family="DejaVu Sans Mono, monospace" font-size="14" xml:space="preserve">
{body}
</g>
</svg>
""".format(width=width, height=height, right=width - 28, body="\n".join(body))
    output.mkdir(parents=True, exist_ok=True)
    (output / "demo.svg").write_text(svg, encoding="utf-8")
    (output / "demo.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Rendered demo.svg and demo.txt from actual CLI output (exit 1) in {}.".format(output))


if __name__ == "__main__":
    main()
