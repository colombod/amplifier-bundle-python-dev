"""Tests for module-not-found detection in checker subprocess calls.

Covers the bug where tools not installed as Python modules cause silent
success instead of a TOOL-NOT-FOUND error.
"""

import json
from unittest.mock import MagicMock
from unittest.mock import patch

from amplifier_bundle_python_dev.checker import PythonChecker
from amplifier_bundle_python_dev.models import CheckConfig
from amplifier_bundle_python_dev.models import Severity

# --- Helpers ---


def _make_subprocess_result(returncode: int, stdout: str, stderr: str) -> MagicMock:
    """Return a MagicMock that mimics a subprocess.CompletedProcess."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _checker_with_only(fmt: bool = False, lint: bool = False, types: bool = False) -> PythonChecker:
    """Create a PythonChecker with only the specified checks enabled."""
    config = CheckConfig(
        enable_ruff_format=fmt,
        enable_ruff_lint=lint,
        enable_pyright=types,
        enable_stub_check=False,
    )
    return PythonChecker(config)


# --- ruff-format: module not found ---


@patch("amplifier_bundle_python_dev.checker.subprocess.run")
def test_ruff_format_module_not_found(mock_run):
    """When ruff is not installed as a module, _run_ruff_format returns TOOL-NOT-FOUND."""
    mock_run.return_value = _make_subprocess_result(
        returncode=1,
        stdout="",
        stderr="/usr/bin/python: No module named ruff\n",
    )
    checker = _checker_with_only(fmt=True)
    result = checker.check_files(["some_file.py"])

    tool_not_found = [i for i in result.issues if i.code == "TOOL-NOT-FOUND"]
    assert len(tool_not_found) == 1, f"Expected 1 TOOL-NOT-FOUND issue, got {len(tool_not_found)}"

    issue = tool_not_found[0]
    assert issue.severity == Severity.ERROR, f"Expected ERROR severity, got {issue.severity}"
    assert issue.source == "ruff-format", f"Expected source 'ruff-format', got '{issue.source}'"
    assert "ruff" in issue.message, f"Expected 'ruff' in message, got '{issue.message}'"
    assert "uv add ruff" in issue.message, f"Expected 'uv add ruff' in message, got '{issue.message}'"


@patch("amplifier_bundle_python_dev.checker.subprocess.run")
def test_ruff_format_normal_nonzero_not_false_positive(mock_run):
    """A real ruff format diff (returncode=1, no module error) must NOT produce TOOL-NOT-FOUND."""
    diff_output = "--- a/some_file.py\n+++ b/some_file.py\n@@ -1,2 +1,2 @@\n-x=1\n+x = 1\n"
    mock_run.return_value = _make_subprocess_result(
        returncode=1,
        stdout=diff_output,
        stderr="",
    )
    checker = _checker_with_only(fmt=True)
    result = checker.check_files(["some_file.py"])

    tool_not_found = [i for i in result.issues if i.code == "TOOL-NOT-FOUND"]
    assert len(tool_not_found) == 0, f"Normal format diff should not produce TOOL-NOT-FOUND, got: {tool_not_found}"


# --- ruff-lint: module not found ---


@patch("amplifier_bundle_python_dev.checker.subprocess.run")
def test_ruff_lint_module_not_found(mock_run):
    """When ruff is not installed as a module, _run_ruff_lint returns TOOL-NOT-FOUND."""
    mock_run.return_value = _make_subprocess_result(
        returncode=1,
        stdout="",
        stderr="/usr/bin/python: No module named ruff\n",
    )
    checker = _checker_with_only(lint=True)
    result = checker.check_files(["some_file.py"])

    tool_not_found = [i for i in result.issues if i.code == "TOOL-NOT-FOUND"]
    assert len(tool_not_found) == 1, f"Expected 1 TOOL-NOT-FOUND issue, got {len(tool_not_found)}"

    issue = tool_not_found[0]
    assert issue.severity == Severity.ERROR, f"Expected ERROR severity, got {issue.severity}"
    assert issue.source == "ruff-lint", f"Expected source 'ruff-lint', got '{issue.source}'"
    assert "ruff" in issue.message, f"Expected 'ruff' in message, got '{issue.message}'"
    assert "uv add ruff" in issue.message, f"Expected 'uv add ruff' in message, got '{issue.message}'"


@patch("amplifier_bundle_python_dev.checker.subprocess.run")
def test_ruff_lint_normal_nonzero_not_false_positive(mock_run):
    """A real ruff lint result with issues (returncode=1) must NOT produce TOOL-NOT-FOUND.

    Should still parse the real F401 issue from JSON output.
    """
    lint_json = json.dumps(
        [
            {
                "filename": "some_file.py",
                "location": {"row": 1, "column": 1},
                "end_location": {"row": 1, "column": 14},
                "code": "F401",
                "message": "'os' imported but unused",
                "fix": None,
                "url": "https://docs.astral.sh/ruff/rules/unused-import",
            }
        ]
    )
    mock_run.return_value = _make_subprocess_result(
        returncode=1,
        stdout=lint_json,
        stderr="",
    )
    checker = _checker_with_only(lint=True)
    result = checker.check_files(["some_file.py"])

    tool_not_found = [i for i in result.issues if i.code == "TOOL-NOT-FOUND"]
    assert len(tool_not_found) == 0, f"Real lint output should not produce TOOL-NOT-FOUND, got: {tool_not_found}"

    f401_issues = [i for i in result.issues if i.code == "F401"]
    assert len(f401_issues) == 1, f"Expected 1 F401 issue to be parsed, got {len(f401_issues)}"


# --- pyright: module not found ---


@patch("amplifier_bundle_python_dev.checker.subprocess.run")
def test_pyright_module_not_found(mock_run):
    """When pyright is not installed as a module, _run_pyright returns TOOL-NOT-FOUND."""
    mock_run.return_value = _make_subprocess_result(
        returncode=1,
        stdout="",
        stderr="/usr/bin/python: No module named pyright\n",
    )
    checker = _checker_with_only(types=True)
    result = checker.check_files(["some_file.py"])

    tool_not_found = [i for i in result.issues if i.code == "TOOL-NOT-FOUND"]
    assert len(tool_not_found) == 1, f"Expected 1 TOOL-NOT-FOUND issue, got {len(tool_not_found)}"

    issue = tool_not_found[0]
    assert issue.severity == Severity.ERROR, f"Expected ERROR severity, got {issue.severity}"
    assert issue.source == "pyright", f"Expected source 'pyright', got '{issue.source}'"
    assert "pyright" in issue.message, f"Expected 'pyright' in message, got '{issue.message}'"
    assert "uv add pyright" in issue.message, f"Expected 'uv add pyright' in message, got '{issue.message}'"


@patch("amplifier_bundle_python_dev.checker.subprocess.run")
def test_pyright_normal_nonzero_not_false_positive(mock_run):
    """A real pyright result with type errors (returncode=1) must NOT produce TOOL-NOT-FOUND."""
    pyright_json = json.dumps(
        {
            "version": "1.1.350",
            "generalDiagnostics": [
                {
                    "file": "some_file.py",
                    "severity": "error",
                    "message": 'Cannot access attribute "foo" for class "Bar"',
                    "rule": "reportAttributeAccessIssue",
                    "range": {
                        "start": {"line": 4, "character": 0},
                        "end": {"line": 4, "character": 7},
                    },
                }
            ],
            "summary": {"filesAnalyzed": 1, "errorCount": 1, "warningCount": 0},
        }
    )
    mock_run.return_value = _make_subprocess_result(
        returncode=1,
        stdout=pyright_json,
        stderr="",
    )
    checker = _checker_with_only(types=True)
    result = checker.check_files(["some_file.py"])

    tool_not_found = [i for i in result.issues if i.code == "TOOL-NOT-FOUND"]
    assert len(tool_not_found) == 0, f"Real pyright output should not produce TOOL-NOT-FOUND, got: {tool_not_found}"

    type_issues = [i for i in result.issues if i.code == "reportAttributeAccessIssue"]
    assert len(type_issues) == 1, f"Expected 1 type error to be parsed, got {len(type_issues)}"


# --- Regression guards: FileNotFoundError still works ---


@patch("amplifier_bundle_python_dev.checker.subprocess.run")
def test_ruff_format_file_not_found_still_works(mock_run):
    """FileNotFoundError on subprocess still returns TOOL-NOT-FOUND for ruff-format."""
    mock_run.side_effect = FileNotFoundError("ruff not found")
    checker = _checker_with_only(fmt=True)
    result = checker.check_files(["some_file.py"])

    tool_not_found = [i for i in result.issues if i.code == "TOOL-NOT-FOUND"]
    assert len(tool_not_found) == 1, (
        f"FileNotFoundError should produce TOOL-NOT-FOUND, got {len(tool_not_found)} issues"
    )
    assert tool_not_found[0].source == "ruff-format"


@patch("amplifier_bundle_python_dev.checker.subprocess.run")
def test_ruff_lint_file_not_found_still_works(mock_run):
    """FileNotFoundError on subprocess still returns TOOL-NOT-FOUND for ruff-lint."""
    mock_run.side_effect = FileNotFoundError("ruff not found")
    checker = _checker_with_only(lint=True)
    result = checker.check_files(["some_file.py"])

    tool_not_found = [i for i in result.issues if i.code == "TOOL-NOT-FOUND"]
    assert len(tool_not_found) == 1, (
        f"FileNotFoundError should produce TOOL-NOT-FOUND, got {len(tool_not_found)} issues"
    )
    assert tool_not_found[0].source == "ruff-lint"


@patch("amplifier_bundle_python_dev.checker.subprocess.run")
def test_pyright_file_not_found_still_works(mock_run):
    """FileNotFoundError on subprocess still returns TOOL-NOT-FOUND for pyright."""
    mock_run.side_effect = FileNotFoundError("pyright not found")
    checker = _checker_with_only(types=True)
    result = checker.check_files(["some_file.py"])

    tool_not_found = [i for i in result.issues if i.code == "TOOL-NOT-FOUND"]
    assert len(tool_not_found) == 1, (
        f"FileNotFoundError should produce TOOL-NOT-FOUND, got {len(tool_not_found)} issues"
    )
    assert tool_not_found[0].source == "pyright"
