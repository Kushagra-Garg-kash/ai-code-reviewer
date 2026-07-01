"""
frontend/streamlit_app.py

Streamlit frontend for the AI-Powered Code Reviewer.
Connects to the FastAPI backend via HTTP and renders review results.

Week 3, Day 1 — core layout and backend connection.
Week 3, Day 2 — color-coded severity badges, issue breakdown, polished cards.
"""
import sys
import os
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests
import streamlit as st
from app.report_generator import generate_markdown_report
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

APP_API_KEY = os.getenv("APP_API_KEY")
# Backend URL — switch to Render URL when deployed in Week 4
BACKEND_URL = "http://127.0.0.1:8000"

# ---------------------------------------------------------------------------
# Severity badge helpers
# ---------------------------------------------------------------------------

# Color map for severity levels — used in HTML badges
SEVERITY_COLORS: dict[str, str] = {
    "critical":   "#ff4b4b",  # red
    "warning":    "#ffa500",  # orange
    "suggestion": "#1c83e1",  # blue
}

SEVERITY_ICONS: dict[str, str] = {
    "critical":   "🔴",
    "warning":    "🟡",
    "suggestion": "🔵",
}


def severity_badge(severity: str) -> str:
    """
    Returns an HTML badge string for a given severity level.
    Rendered via st.markdown(..., unsafe_allow_html=True).

    Why HTML and not st.badge()?
    Streamlit has no native badge widget. HTML via markdown is the standard
    approach — and a good thing to know how to explain in an interview.
    """
    color = SEVERITY_COLORS.get(severity, "#888888")
    label = severity.upper()
    return (
        f'<span style="'
        f"background-color: {color}; "
        f"color: white; "
        f"padding: 2px 10px; "
        f"border-radius: 12px; "
        f"font-size: 0.75em; "
        f"font-weight: bold; "
        f'letter-spacing: 0.05em;">'
        f"{label}</span>"
    )


def issue_breakdown(issues: list[dict]) -> dict[str, int]:
    """
    Returns a count of issues per severity level.
    Used to render the summary row above the issue list.
    """
    counts: dict[str, int] = {"critical": 0, "warning": 0, "suggestion": 0}
    for issue in issues:
        sev = issue.get("severity", "suggestion")
        if sev in counts:
            counts[sev] += 1
    return counts


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Code Reviewer",
    page_icon="🔍",
    layout="centered",
)

st.title(" AI-Powered Code Reviewer")
st.caption(
    "Paste a GitHub Pull Request URL below. "
    "The tool runs static analysis + LLM reasoning and returns structured issues."
)

st.divider()

# ---------------------------------------------------------------------------
# Sidebar — Review History
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Review History")
    st.caption("Last 10 reviews")

    try:
        history_response = requests.get(f"{BACKEND_URL}/reviews", params={"limit": 10}, timeout=10)

        if history_response.status_code == 200:
            history = history_response.json()

            if not history:
                st.caption("No reviews yet. Run your first review to see it here.")
            else:
                for entry in history:
                    issue_count = entry.get("issue_count", 0)
                    critical = entry.get("critical_count", 0)

                    # Short PR display: just owner/repo#number if we can parse it
                    pr_url_display = entry.get("pr_url", "—")

                    timestamp_raw = entry.get("timestamp", "")
                    timestamp_display = "—"
                    if timestamp_raw:
                        try:
                            utc_dt = datetime.fromisoformat(timestamp_raw)
                            ist_dt = utc_dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
                            timestamp_display = ist_dt.strftime("%d %b, %I:%M %p").lstrip("0").replace(" 0", " ")
                        except ValueError:
                            timestamp_display = timestamp_raw[:16]

                    repo_short = pr_url_display.replace("https://github.com/", "")

                    st.markdown(
                        f"""
                        <div style="
                            border-left: 3px solid {'#ff4b4b' if critical > 0 else ('#ffa500' if issue_count > 0 else '#2da44e')};
                            padding: 6px 0 6px 12px;
                            margin-bottom: 14px;
                        ">
                            <div style="font-size: 0.85em; color: #1a1a1a; font-weight: 600;">
                                {issue_count} issue{'s' if issue_count != 1 else ''}
                            </div>
                            <div style="font-size: 0.78em; color: #8b8b8b; margin-top: 2px;">
                                {timestamp_display}
                            </div>
                            <div style="font-size: 0.78em; margin-top: 4px;">
                                <a href="{pr_url_display}" target="_blank" style="color: #57606a; text-decoration: none;">
                                    {repo_short}
                                </a>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        else:
            st.caption("Could not load review history.")

    except requests.exceptions.RequestException:
        st.caption("Backend not reachable — history unavailable.")

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

pr_url = st.text_input(
    label="GitHub PR URL",
    placeholder="https://github.com/owner/repo/pull/123",
    help="Must be a public repository. Only Python files are analyzed in v0.1.",
)

submit = st.button("Run Review", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Review pipeline — runs when the button is clicked
# ---------------------------------------------------------------------------

if submit:
    if not pr_url.strip():
        st.warning("Please enter a GitHub PR URL before submitting.")
        st.stop()

    with st.spinner("Fetching PR diff and running analysis..."):
        try:
            response = requests.post(
                f"{BACKEND_URL}/review",
                json={"pr_url": pr_url.strip()},
                headers={"X-API-Key": APP_API_KEY},
                timeout=60,  # LLM calls can take 10–20s on free tier
            )

            # Handle non-2xx responses from the backend
            if response.status_code != 200:
                detail = response.json().get("detail", "Unknown error from backend.")
                st.error(f"Backend returned {response.status_code}: {detail}")
                st.stop()

            data = response.json()

        except requests.exceptions.ConnectionError:
            st.error(
                "Could not connect to the backend. "
                "Make sure the FastAPI server is running at "
                f"`{BACKEND_URL}`."
            )
            st.stop()

        except requests.exceptions.Timeout:
            st.error("The request timed out. The PR may be too large — try a smaller one.")
            st.stop()

    # -----------------------------------------------------------------------
    # Results
    # -----------------------------------------------------------------------

    st.divider()

    # --- PR Metadata Card ---
    meta = data.get("metadata", {})

    state = meta.get("state", "unknown").lower()
    state_color = "#2da44e" if state == "open" else "#8250df"  # green open, purple closed
    state_badge = (
        f'<span style="background-color: {state_color}; color: white; '
        f'padding: 2px 10px; border-radius: 12px; font-size: 0.8em; '
        f'font-weight: bold;">{state.capitalize()}</span>'
    )

    base = meta.get("base_branch", "—")
    head = meta.get("head_branch", "—")

    st.markdown(
        f"""
        <div style="
            background-color: #f6f8fa;
            border: 1px solid #d0d7de;
            border-radius: 10px;
            padding: 20px 24px;
            margin-bottom: 16px;
        ">
            <div style="font-size: 1.2em; font-weight: 700; margin-bottom: 10px;">
                📋 {meta.get('title', 'PR Review')}
            </div>
            <div style="color: #57606a; font-size: 0.9em; margin-bottom: 12px;">
                👤 <b>{meta.get('author', '—')}</b> &nbsp;•&nbsp;
                   <code>{head}</code> → <code>{base}</code> &nbsp;•&nbsp;
                {state_badge}
            </div>
            <div style="display: flex; gap: 24px; font-size: 0.9em;">
                <span>📁 <b>{data.get('files_analyzed', 0)}</b> file(s) analyzed</span>
                <span>⚠️ <b>{len(data.get('issues', []))}</b> issue(s) found</span>
                <span>📝 <b>{data.get('total_added_lines', 0)}</b> lines added</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # --- Early exit: no issues ---
    issues = data.get("issues", [])

    if not issues:
        st.success(
            "✅ No issues found. Static analysis returned zero findings — "
            "LLM was not called."
        )
        st.stop()

    # --- LLM not called (zero static issues) ---
    if not data.get("llm_called"):
        st.info("Static analysis found no issues. LLM review was skipped.")
        st.stop()

    # --- Severity breakdown row ---
    breakdown = issue_breakdown(issues)

    st.subheader(f" Issues ({len(issues)} found)")

    st.markdown(
        f"""
        <div style="
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            margin-top: 8px;
        ">
            <div style="
                background-color: #fff1f1;
                border: 1px solid #ff4b4b;
                border-radius: 8px;
                padding: 10px 20px;
                text-align: center;
                min-width: 100px;
            ">
                <div style="font-size: 1.4em; font-weight: 700; color: #ff4b4b;">
                    {breakdown['critical']}
                </div>
                <div style="font-size: 0.78em; color: #ff4b4b; font-weight: 600;">
                    CRITICAL
                </div>
            </div>
            <div style="
                background-color: #fff8f0;
                border: 1px solid #ffa500;
                border-radius: 8px;
                padding: 10px 20px;
                text-align: center;
                min-width: 100px;
            ">
                <div style="font-size: 1.4em; font-weight: 700; color: #ffa500;">
                    {breakdown['warning']}
                </div>
                <div style="font-size: 0.78em; color: #ffa500; font-weight: 600;">
                    WARNING
                </div>
            </div>
            <div style="
                background-color: #f0f6ff;
                border: 1px solid #1c83e1;
                border-radius: 8px;
                padding: 10px 20px;
                text-align: center;
                min-width: 100px;
            ">
                <div style="font-size: 1.4em; font-weight: 700; color: #1c83e1;">
                    {breakdown['suggestion']}
                </div>
                <div style="font-size: 0.78em; color: #1c83e1; font-weight: 600;">
                    SUGGESTION
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption("Ordered by severity — critical first.")
    st.write("")  # small spacer

    # --- Issue cards ---
    for issue in issues:
        severity = issue.get("severity", "suggestion")
        title = issue.get("issue_title", "Issue")
        line = issue.get("line_number", "?")
        icon = SEVERITY_ICONS.get(severity, "⚪")

        # Expander label — icon + title + line number
        label = f"{icon} Line {line} — {title}"

        with st.expander(label, expanded=(severity == "critical")):

            # Severity badge inline
            st.markdown(severity_badge(severity), unsafe_allow_html=True)
            st.write("")  # spacer after badge

            # Explanation
            st.markdown("**📖 Explanation**")
            st.write(issue.get("explanation", "—"))

            # Fix suggestion
            st.markdown("**🔧 Fix Suggestion**")
            st.code(issue.get("fix_suggestion", "—"), language=None)

    # --- Report generator ---
    st.divider()
    report_md = generate_markdown_report(data)
 
    st.download_button(
        label="⬇️ Download Markdown Report",
        data=report_md,
        file_name=f"review_{meta.get('repo', 'report').replace('/', '_')}_pr{meta.get('pr_number', '')}.md",
        mime="text/markdown",
        use_container_width=True,
    )

    # --- Summary stats footer ---
    st.divider()
    st.caption(
        f"Static issues found: {data.get('static_issues_found', 0)} · "
        f"Total added lines: {data.get('total_added_lines', 0)} · "
        f"LLM called: {data.get('llm_called', False)}"
    )