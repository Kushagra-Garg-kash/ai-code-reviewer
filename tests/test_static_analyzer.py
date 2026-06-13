"""
tests/test_static_analyzer.py

Unit tests for static_analyzer.py.
Tests _normalize_bandit() and _normalize_pylint() directly.

These are private functions (prefixed with _), but testing them directly
is the right call here — they contain the core logic we care about, and
testing only analyze_files() would require subprocess mocking which is
significantly more complex.
"""

from app.static_analyzer import (
    _normalize_bandit,
    _normalize_pylint,
    PYLINT_IGNORED_SYMBOLS,
)


# ---------------------------------------------------------------------------
# _normalize_bandit tests
# ---------------------------------------------------------------------------

def test_normalize_bandit_severity_mapping(sample_bandit_raw):
    """
    Bandit severity levels (HIGH/MEDIUM/LOW) must map to our unified scale
    (critical/warning/suggestion).
    Uses sample_bandit_raw fixture from conftest.py.
    """
    result = _normalize_bandit(sample_bandit_raw)

    # B105 is MEDIUM → should map to "warning"
    b105 = next(i for i in result if i["rule_id"] == "B105")
    assert b105["severity"] == "warning"

    # B608 is HIGH → should map to "critical"
    b608 = next(i for i in result if i["rule_id"] == "B608")
    assert b608["severity"] == "critical"


def test_normalize_bandit_output_shape(sample_bandit_raw):
    """
    Every normalized bandit issue must have exactly the 5 required keys.
    """
    result = _normalize_bandit(sample_bandit_raw)

    required_keys = {"line", "severity", "rule_id", "message", "source"}
    for issue in result:
        assert required_keys == set(issue.keys()), (
            f"Issue is missing keys. Got: {set(issue.keys())}"
        )


def test_normalize_bandit_source_tag(sample_bandit_raw):
    """
    All bandit issues must have source == "bandit".
    """
    result = _normalize_bandit(sample_bandit_raw)
    assert all(i["source"] == "bandit" for i in result)


def test_normalize_bandit_line_offset(sample_bandit_raw):
    """
    line_offset should subtract from the reported line number.
    Used when the temp file had a wrapper function injected at line 1.
    """
    result = _normalize_bandit(sample_bandit_raw, line_offset=1)

    # B105 was at line 4 → should now be line 3
    b105 = next(i for i in result if i["rule_id"] == "B105")
    assert b105["line"] == 3


# ---------------------------------------------------------------------------
# _normalize_pylint tests
# ---------------------------------------------------------------------------

def test_normalize_pylint_filters_ignored_symbols(sample_pylint_raw):
    """
    Symbols in PYLINT_IGNORED_SYMBOLS must be excluded from the output.
    sample_pylint_raw contains 'missing-module-docstring' which is in the
    ignored set — it should not appear in results.
    """
    result = _normalize_pylint(sample_pylint_raw)

    returned_symbols = [i["rule_id"] for i in result]
    for ignored in PYLINT_IGNORED_SYMBOLS:
        assert ignored not in returned_symbols, (
            f"Ignored symbol '{ignored}' appeared in normalized output."
        )


def test_normalize_pylint_keeps_real_warnings(sample_pylint_raw):
    """
    Real warnings (not in the ignored set) must be kept in the output.
    'unused-variable' (W0612) is a real warning and must be present.
    """
    result = _normalize_pylint(sample_pylint_raw)

    rule_ids = [i["rule_id"] for i in result]
    assert "W0612" in rule_ids


def test_normalize_pylint_source_tag(sample_pylint_raw):
    """
    All pylint issues must have source == "pylint".
    """
    result = _normalize_pylint(sample_pylint_raw)
    assert all(i["source"] == "pylint" for i in result)


def test_normalize_pylint_output_shape(sample_pylint_raw):
    """
    Every normalized pylint issue must have exactly the 5 required keys.
    """
    result = _normalize_pylint(sample_pylint_raw)

    required_keys = {"line", "severity", "rule_id", "message", "source"}
    for issue in result:
        assert required_keys == set(issue.keys())