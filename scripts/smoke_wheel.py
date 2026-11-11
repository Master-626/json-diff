"""Install and exercise the built wheel in isolation on Windows, macOS and Linux."""

import json
import os
import subprocess
import tempfile
import venv
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    wheels = list((ROOT / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Build exactly one wheel before running this smoke test.")
    with tempfile.TemporaryDirectory(prefix="json-diff-wheel-") as directory:
        work = Path(directory)
        environment = work / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", str(wheels[0])], check=True)
        cli = environment / ("Scripts/json-diff.exe" if os.name == "nt" else "bin/json-diff")

        def run(*arguments):
            return subprocess.run(
                [str(cli), *map(str, arguments)],
                cwd=work,
                capture_output=True,
                text=True,
            )

        equal = run(
            "compare",
            ROOT / "examples/expected.json",
            ROOT / "examples/equivalent.json",
            "--ignore",
            "request_id",
            "--ignore",
            "generated_at",
            "--json-output",
        )
        assert equal.returncode == 0 and json.loads(equal.stdout) == [], equal
        old, new = work / "old.json", work / "new.json"
        old.write_text("[0.10000000000000000, 0.0]", encoding="utf-8")
        new.write_text("[0.10000000000000001, 1e-400]", encoding="utf-8")
        default = run("compare", old, new, "--json-output")
        assert default.returncode == 0 and json.loads(default.stdout) == [], default
        exact = run("compare", old, new, "--json-output", "--exact-decimals")
        assert exact.returncode == 1 and exact.stderr == "", exact
        diffs = json.loads(exact.stdout, parse_float=Decimal)
        assert [diff["new_value"] for diff in diffs] == [
            Decimal("0.10000000000000001"),
            Decimal("1e-400"),
        ]
        base, extra = work / "base.json", work / "extra.json"
        base.write_text('{"role": "reader"}', encoding="utf-8")
        extra.write_text('{"role": "reader", "extra": 1}', encoding="utf-8")
        added = run("compare", base, extra, "--ignore-added", "--json-output")
        assert added.returncode == 0 and json.loads(added.stdout) == [], added
        output = work / "report.html"
        report = run("report", old, new, "--exact-decimals", "--fail-on-diff", "-o", output)
        assert report.returncode == 1 and report.stderr == "", report
        html = output.read_text(encoding="utf-8")
        assert "0.10000000000000001" in html and "1E-400" in html
    print("Installed-wheel smoke test passed: default, exact JSON, exact HTML and ignore-added.")


if __name__ == "__main__":
    main()
