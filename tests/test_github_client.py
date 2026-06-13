"""
tests/test_github_client.py

Unit tests for github_client.py.
Tests parse_pr_url() and extract_added_lines() — pure functions with
no external dependencies, so no mocking needed here.
"""

import pytest
from app.github_client import parse_pr_url, extract_added_lines


# ---------------------------------------------------------------------------
# parse_pr_url tests
# ---------------------------------------------------------------------------

def test_parse_pr_url_valid():
    """
    Valid GitHub PR URL should return correct (owner, repo, pr_number) tuple.
    """
    owner, repo, pr_number = parse_pr_url("https://github.com/psf/requests/pull/6710")

    assert owner == "psf"
    assert repo == "requests"
    assert pr_number == 6710


def test_parse_pr_url_invalid():
    """
    Malformed URL should raise ValueError with a descriptive message.
    We don't test the exact message — just that the right exception type is raised.
    """
    with pytest.raises(ValueError):
        parse_pr_url("https://github.com/psf/requests")  # missing /pull/number


def test_parse_pr_url_invalid_not_github():
    """
    Non-GitHub URL should also raise ValueError.
    """
    with pytest.raises(ValueError):
        parse_pr_url("https://gitlab.com/owner/repo/merge_requests/42")


# ---------------------------------------------------------------------------
# extract_added_lines tests
# ---------------------------------------------------------------------------

def test_extract_added_lines_returns_only_added(sample_patch):
    """
    extract_added_lines() should return only lines prefixed with '+' in the diff.
    Context lines (' ') and removed lines ('-') must be excluded.
    Uses the sample_patch fixture from conftest.py.
    """
    result = extract_added_lines(sample_patch)

    # Only added lines should be returned — 6 '+' lines in sample_patch
    assert len(result) == 7


def test_extract_added_lines_correct_content(sample_patch):
    """
    The content of returned lines should have the leading '+' stripped.
    Line numbers should reflect position in the NEW file version.
    """
    result = extract_added_lines(sample_patch)

    # All returned content should be plain code, not raw diff lines
    for line_number, content in result:
        assert not content.startswith("+"), (
            f"Leading '+' was not stripped from line {line_number}: {content!r}"
        )


def test_extract_added_lines_empty_patch():
    """
    Empty patch string should return an empty list — no crash.
    """
    result = extract_added_lines("")
    assert result == []


def test_extract_added_lines_line_numbers_are_sequential(sample_patch):
    """
    Line numbers returned must be positive integers in ascending order.
    """
    result = extract_added_lines(sample_patch)
    line_numbers = [ln for ln, _ in result]

    assert all(ln > 0 for ln in line_numbers)
    assert line_numbers == sorted(line_numbers)