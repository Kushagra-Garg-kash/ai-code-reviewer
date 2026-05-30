"""
static_analyzer.py

Responsible for running static analysis tools (bandit + pylint) on code
extracted from GitHub PR diffs and normalizing their output into a single
unified issue format for downstream LLM processing.
"""

import json
import os
import subprocess
import tempfile
from typing import Any


# ---------------------------------------------------------------------------
# Severity mapping — normalize each tool's scale to our unified scale
# ---------------------------------------------------------------------------

BANDIT_SEVERITY_MAP: dict[str, str] = {
    "HIGH": "critical",
    "MEDIUM": "warning",
    "LOW": "suggestion",
}

PYLINT_SEVERITY_MAP: dict[str, str] = {
    "error": "critical",
    "warning": "warning",
    "refactor": "suggestion",
    "convention": "suggestion",
}

# Pylint message types we deliberately ignore — pure style noise
# that adds no value to a code review focused on bugs and security.
PYLINT_IGNORED_SYMBOLS: set[str] = {
    "missing-module-docstring",
    "missing-function-docstring",
    "missing-class-docstring",
    "trailing-whitespace",
    "missing-final-newline",
    "line-too-long",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_temp_file(lines: list[tuple[int, str]]) -> tuple[str, int]:
    """
    Writes added lines to a temporary .py file for tool analysis.

    Line numbers are preserved by padding with empty lines so that
    bandit/pylint report the correct original line numbers.

    If any added line is indented (i.e. comes from inside a function/class),
    we wrap the entire block in a dummy function to prevent syntax errors.
    The dummy function definition is inserted at line 1, so all original
    line numbers shift by 1 — we correct for this via the line_offset return value.

    Args:
        lines: List of (line_number, line_content) tuples from extract_added_lines().

    Returns:
        A tuple of (temp_file_path, line_offset).
        line_offset is 1 if we added a wrapper, 0 otherwise.
    """
    if not lines:
        return "", 0

    max_line = max(ln for ln, _ in lines)

    # Check if any line is indented — if so, we need a wrapper
    needs_wrapper = any(content.startswith((" ", "\t")) for _, content in lines)

    # Build the file contents as a list indexed by line number
    file_lines: list[str] = [""] * max_line
    for line_number, content in lines:
        file_lines[line_number - 1] = content

    if needs_wrapper:
        # Prepend a dummy function definition — all lines shift down by 1
        wrapped = ["def _review_target():"]
        for line in file_lines:
            if line.strip() == "":
                wrapped.append("")
            elif line.startswith((" ", "\t")):
                wrapped.append(line)         # already indented
            else:
                wrapped.append("    " + line)  # add one indent level
        file_content = "\n".join(wrapped)
        line_offset = 1
    else:
        file_content = "\n".join(file_lines)
        line_offset = 0

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        encoding="utf-8",
    )
    tmp.write(file_content)
    tmp.close()

    return tmp.name, line_offset


def _run_bandit(filepath: str) -> list[dict[str, Any]]:
    """
    Runs bandit on a file and returns its raw results list.

    Args:
        filepath: Absolute path to the temporary Python file.

    Returns:
        List of raw bandit result dicts, or empty list if bandit fails.
    """
    try:
        result = subprocess.run(
            ["bandit", "-f", "json", "-q", filepath],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # bandit exits with code 1 when it finds issues — that's expected,
        # not an error. We only treat it as a failure if stdout is empty.
        if not result.stdout.strip():
            return []

        data = json.loads(result.stdout)
        return data.get("results", [])

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def _run_pylint(filepath: str) -> list[dict[str, Any]]:
    """
    Runs pylint on a file and returns its raw results list.

    Args:
        filepath: Absolute path to the temporary Python file.

    Returns:
        List of raw pylint result dicts, or empty list if pylint fails.
    """
    try:
        result = subprocess.run(
            ["pylint", "--output-format=json", filepath],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if not result.stdout.strip():
            return []

        return json.loads(result.stdout)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def _normalize_bandit(
    raw_results: list[dict[str, Any]],
    line_offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Converts bandit's raw output into the unified issue format.

    Args:
        raw_results: The 'results' list from bandit's JSON output.
        line_offset: Number of lines to subtract due to wrapper injection.

    Returns:
        List of normalized issue dicts.
    """
    normalized = []

    for issue in raw_results:
        severity_raw = issue.get("issue_severity", "LOW")
        severity = BANDIT_SEVERITY_MAP.get(severity_raw, "suggestion")
        reported_line = issue.get("line_number", 0)

        normalized.append({
            "line": max(1, reported_line - line_offset),
            "severity": severity,
            "rule_id": issue.get("test_id", "UNKNOWN"),
            "message": issue.get("issue_text", ""),
            "source": "bandit",
        })

    return normalized


def _normalize_pylint(
    raw_results: list[dict[str, Any]],
    line_offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Converts pylint's raw output into the unified issue format.
    Filters out noise-only convention messages defined in PYLINT_IGNORED_SYMBOLS.

    Args:
        raw_results: The root list from pylint's JSON output.
        line_offset: Number of lines to subtract due to wrapper injection.

    Returns:
        List of normalized issue dicts.
    """
    normalized = []

    for issue in raw_results:
        symbol = issue.get("symbol", "")

        # Skip symbols we've explicitly decided are too noisy
        if symbol in PYLINT_IGNORED_SYMBOLS:
            continue

        type_raw = issue.get("type", "convention")
        severity = PYLINT_SEVERITY_MAP.get(type_raw, "suggestion")
        reported_line = issue.get("line", 0)

        normalized.append({
            "line": max(1, reported_line - line_offset),
            "severity": severity,
            "rule_id": issue.get("message-id", "UNKNOWN"),
            "message": issue.get("message", ""),
            "source": "pylint",
        })

    return normalized


def _deduplicate(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Removes duplicate issues at the same line from the same source.

    Deduplicates by (line, rule_id) to keep the output clean.

    Args:
        issues: Combined list of normalized issues from both tools.

    Returns:
        Deduplicated list, preserving original order.
    """
    seen: set[tuple[int, str]] = set()
    unique = []

    for issue in issues:
        key = (issue["line"], issue["rule_id"])
        if key not in seen:
            seen.add(key)
            unique.append(issue)

    return unique


# ---------------------------------------------------------------------------
# Public interface — this is what the rest of the app calls
# ---------------------------------------------------------------------------

def analyze_files(
    files: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """
    Runs bandit and pylint on each Python file's added lines and returns
    a mapping of filename → list of normalized issues.

    This is the only function imported by other modules.

    Args:
        files: The 'files' list from get_python_diffs_from_pr(). Each dict has:
               - filename: str
               - added_lines: list of (line_number, line_content) tuples

    Returns:
        Dict mapping filename (str) → list of issue dicts.
        Each issue dict has: line, severity, rule_id, message, source.
        Files with zero issues are included with an empty list.

    Example return value:
        {
            "app/main.py": [
                {
                    "line": 9,
                    "severity": "warning",
                    "rule_id": "B608",
                    "message": "Possible SQL injection...",
                    "source": "bandit"
                }
            ]
        }
    """
    results: dict[str, list[dict[str, Any]]] = {}

    for file in files:
        filename = file["filename"]
        added_lines = file.get("added_lines", [])

        if not added_lines:
            results[filename] = []
            continue

        tmp_path, line_offset = _write_temp_file(added_lines)

        try:
            bandit_raw = _run_bandit(tmp_path)
            pylint_raw = _run_pylint(tmp_path)

            bandit_issues = _normalize_bandit(bandit_raw, line_offset)
            pylint_issues = _normalize_pylint(pylint_raw, line_offset)

            combined = bandit_issues + pylint_issues
            results[filename] = _deduplicate(combined)

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    return results


# ---------------------------------------------------------------------------
# Quick test — remove this block before Week 3
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_files = [
        {
            "filename": "sample_vulnerable.py",
            "added_lines": [
                (5, "    # Hardcoded credentials"),
                (6, "    password = 'admin123'"),
                (9, "    query = 'SELECT * FROM users WHERE id = ' + user_id"),
                (16, "    return pickle.load(f)"),
            ],
        }
    ]

    output = analyze_files(test_files)

    for fname, issues in output.items():
        print(f"\n=== {fname} — {len(issues)} issues ===")
        for issue in issues:
            print(f"  Line {issue['line']:3} | {issue['severity']:10} | "
                  f"{issue['rule_id']:6} | [{issue['source']}] {issue['message']}")