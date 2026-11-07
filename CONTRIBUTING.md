# Contributing

Useful contributions start with a reproducible comparison case. Use synthetic or sanitized JSON; do not attach credentials, access tokens or personal data.

## Local checks

```bash
python -m venv .venv
# Activate .venv using the command for your shell, then:
python -m pip install -e '.[dev]'
python -m pytest --cov=json_diff --cov-report=term-missing
ruff check .
ruff format --check .
python -m build
```

Tests cover core comparison, escaped JSON Pointers, ignore rules, strict input parsing, stdout/stderr and exit codes, stdin, HTML injection, and protection against overwriting input files. Coverage is a regression check, not proof that all edge cases are handled.

Add a failing regression test before fixing a bug. For a new option, test both CLI commands where applicable, document its interaction with ignore rules, and state what happens when inputs are invalid. Keep supported Python versions working and avoid introducing network access to the comparison path.

## Reporting a bug

Include the exact command, Python version, operating system, two small JSON inputs, expected output and actual output/exit code. Note whether you installed from a commit or a local checkout. For a suspected vulnerability, avoid including a live exploit against someone else's service or private data in a public issue.

## Scope

The immediate scope is deterministic comparison of saved JSON responses, clear output contracts and useful offline reports. Proposed array matching, numerical tolerance or patch formats need explicit semantics and tests before implementation. No performance or compatibility guarantees should be added without evidence.
