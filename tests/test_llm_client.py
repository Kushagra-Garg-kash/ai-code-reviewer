"""
tests/test_llm_client.py

Unit tests for llm_client.py.
Tests _chunk_issues() and review_code_with_llm() with a mocked Groq client.

The Groq API is NEVER called in these tests. unittest.mock.patch replaces
the real API call with a fake that returns controlled output instantly.
This keeps tests free, fast, and deterministic.
"""

from unittest.mock import patch
from app.llm_client import _chunk_issues, review_code_with_llm


# ---------------------------------------------------------------------------
# _chunk_issues tests
# ---------------------------------------------------------------------------

def test_chunk_issues_splits_correctly(sample_static_issues):
    """
    25 issues with chunk_size=10 should produce 3 chunks: [10, 10, 5].
    Uses sample_static_issues fixture from conftest.py (25 issues).
    """
    chunks = _chunk_issues(sample_static_issues, chunk_size=10)

    assert len(chunks) == 3
    assert len(chunks[0]) == 10
    assert len(chunks[1]) == 10
    assert len(chunks[2]) == 5


def test_chunk_issues_no_split_when_under_limit(sample_static_issues):
    """
    5 issues with chunk_size=10 should return a single chunk — no splitting.
    """
    small = sample_static_issues[:5]
    chunks = _chunk_issues(small, chunk_size=10)

    assert len(chunks) == 1
    assert len(chunks[0]) == 5


def test_chunk_issues_exact_boundary(sample_static_issues):
    """
    Exactly chunk_size issues should return a single chunk, not two.
    Boundary condition: len(issues) == chunk_size → no split.
    """
    exact = sample_static_issues[:10]
    chunks = _chunk_issues(exact, chunk_size=10)

    assert len(chunks) == 1
    assert len(chunks[0]) == 10


def test_chunk_issues_preserves_all_issues(sample_static_issues):
    """
    After chunking, the total number of issues across all chunks must
    equal the original list length — no issues dropped or duplicated.
    """
    chunks = _chunk_issues(sample_static_issues, chunk_size=10)
    total = sum(len(c) for c in chunks)

    assert total == len(sample_static_issues)


# ---------------------------------------------------------------------------
# review_code_with_llm tests — mocked LLM
# ---------------------------------------------------------------------------

# A valid LLM response that matches the ReviewIssue schema exactly.
# This is what ask_llm() would return in a real call.
MOCK_LLM_RESPONSE = """
[
    {
        "line_number": 4,
        "severity": "critical",
        "issue_title": "Hardcoded Password",
        "explanation": "Storing passwords in source code exposes credentials in version control.",
        "fix_suggestion": "Use environment variables or a secrets manager instead."
    }
]
""".strip()


def test_review_code_with_llm_returns_empty_for_no_issues():
    """
    If static_issues is empty, review_code_with_llm() must return []
    immediately without calling the LLM at all.
    """
    # patch ensures ask_llm is never called — if it were, the test would fail
    with patch("app.llm_client.ask_llm") as mock_ask:
        result = review_code_with_llm(
            filename="app/main.py",
            static_issues=[],
            patch="",
        )

    assert result == []
    mock_ask.assert_not_called()


def test_review_code_with_llm_calls_llm_when_issues_exist():
    """
    If static_issues is non-empty, the LLM must be called.
    We mock ask_llm() to return a valid response and verify the result
    is correctly parsed and validated.
    """
    static_issues = [
        {"line": 4, "severity": "critical", "rule_id": "B105", "message": "Hardcoded password", "source": "bandit"}
    ]
    patch_str = "@@ -1,3 +1,6 @@\n import os\n+\n+def login():\n+    password = 'admin123'\n"

    with patch("app.llm_client.ask_llm", return_value=MOCK_LLM_RESPONSE):
        result = review_code_with_llm(
            filename="app/main.py",
            static_issues=static_issues,
            patch=patch_str,
        )

    assert len(result) == 1
    assert result[0]["severity"] == "critical"
    assert result[0]["issue_title"] == "Hardcoded Password"
    assert result[0]["line_number"] == 4