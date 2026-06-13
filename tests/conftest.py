"""
tests/conftest.py

Shared pytest fixtures available to all test files automatically.
No imports needed in individual test files — pytest discovers this file
and injects fixtures by name.
"""

import pytest


@pytest.fixture
def sample_patch():
    """
    A realistic unified diff patch string.
    Used by tests that need extract_added_lines() to parse something real.

    This simulates a PR that adds a vulnerable SQL query and a hardcoded password.
    Line numbers match what GitHub's API would actually return.
    """
    return (
        "@@ -1,3 +1,10 @@\n"
        " import os\n"
        "+\n"
        "+def get_user(user_id):\n"
        "+    password = 'admin123'\n"
        "+    query = 'SELECT * FROM users WHERE id = ' + user_id\n"
        "+    return query\n"
        " \n"
        "+def safe_function():\n"
        "+    pass\n"
    )


@pytest.fixture
def sample_bandit_raw():
    """
    Raw bandit JSON output as returned by _run_bandit().
    Simulates two findings: a hardcoded password and a SQL injection.
    """
    return [
        {
            "test_id": "B105",
            "issue_severity": "MEDIUM",
            "issue_text": "Possible hardcoded password: 'admin123'",
            "line_number": 4,
        },
        {
            "test_id": "B608",
            "issue_severity": "HIGH",
            "issue_text": "Possible SQL injection via string-based query construction.",
            "line_number": 5,
        },
    ]


@pytest.fixture
def sample_pylint_raw():
    """
    Raw pylint JSON output as returned by _run_pylint().
    Simulates one real warning and one ignored convention message.
    """
    return [
        {
            "type": "warning",
            "symbol": "unused-variable",
            "message-id": "W0612",
            "message": "Unused variable 'x'",
            "line": 4,
        },
        {
            "type": "convention",
            "symbol": "missing-module-docstring",  # this should be filtered out
            "message-id": "C0114",
            "message": "Missing module docstring",
            "line": 1,
        },
    ]


@pytest.fixture
def sample_static_issues():
    """
    Normalized static issues in the unified format produced by analyze_files().
    Used by llm_client tests that need static_issues as input.
    """
    return [
        {"line": i, "severity": "warning", "rule_id": f"B10{i}", "message": f"Issue {i}", "source": "bandit"}
        for i in range(1, 26)  # 25 issues — useful for chunking tests
    ]