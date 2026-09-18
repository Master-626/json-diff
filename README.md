# JSON Diff

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI Tool](https://img.shields.io/badge/CI-CI/CD-green.svg)]()

A powerful JSON comparison and diffing CLI tool with colored output and CI/CD support.

## ✨ Features

- **Deep Comparison** - Recursively compares nested objects and arrays
- **Colorized Output** - Beautiful terminal output with Rich
- **Multiple Formats** - Terminal, JSON, HTML report output
- **Ignore Fields** - Skip comparing specific fields (e.g., timestamps, IDs)
- **CI/CD Friendly** - Exit code 1 when differences found
- **Easy to Use** - Simple command-line interface
- **Tested** - Full test suite included

## 📦 Installation

```bash
git clone https://github.com/Master-626/json-diff.git
cd json-diff
pip install .
```

## 🚀 Usage

### Compare Two JSON Files
```bash
json-diff compare file1.json file2.json
```

### Ignore Specific Fields
```bash
json-diff compare file1.json file2.json --ignore timestamp --ignore id
```

### JSON Output (for scripting)
```bash
json-diff compare file1.json file2.json --json-output
```

### Generate HTML Report
```bash
json-diff report file1.json file2.json --output report.html
```

## 🤖 CI/CD Usage

Perfect for validating configuration files in your CI pipeline:

```bash
# Exit 0 if no differences, exit 1 if differences found
json-diff compare expected.json actual.json
```

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest
```

## 📄 License

MIT License
