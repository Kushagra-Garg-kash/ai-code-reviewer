"""
app/llm_client.py

Handles all communication with the LLM provider (Groq).
Abstracted behind a simple ask_llm() function so the rest of the codebase
is completely decoupled from the provider. Switching from Groq to OpenAI
requires changes only in this file.
"""

import os
import json
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# --- Client initialization ---
# Initialized once at module level, not inside each function call.
# This avoids creating a new HTTP client object on every request — a real
# performance concern at scale and a good practice to mention in interviews.
_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Model selection.
# llama3-8b-8192  → fast, free, good for simple tasks
# llama3-70b-8192 → slower, free tier, much better reasoning (use this for code review later)
MODEL = "llama-3.1-8b-instant"


def ask_llm(prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
    """
    Send a prompt to the LLM and return the response as a plain string.

    This function wraps the Groq API call with:
    - Sensible defaults (temperature, max_tokens)
    - Validation of the returned content
    - Structured error handling that separates our errors from provider errors

    Args:
        prompt:        The user's input message.
        system_prompt: Defines the model's role and behavior for this call.
                       Defaults to a generic assistant. Will be replaced with
                       a strict code-review schema prompt in Week 2.

    Returns:
        The model's response as a stripped plain string.

    Raises:
        ValueError:   If the API returns an empty or whitespace-only response.
        RuntimeError: If the API call itself fails (auth error, rate limit,
                      network failure, etc.).
    """
    try:
        response = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=1024,
            temperature=0.2,  # Low temperature = deterministic output.
                               # Critical for code review — we want consistent
                               # results, not creative variation.
        )

        content = response.choices[0].message.content

        if not content or not content.strip():
            raise ValueError("LLM returned an empty response.")

        return content.strip()

    except ValueError:
        # Re-raise our own validation errors exactly as-is.
        raise

    except Exception as e:
        # Catch ALL Groq SDK exceptions (auth failure, rate limit, timeout,
        # network error) and wrap them in a RuntimeError with a clean message.
        # This means the caller (main.py) only needs to handle two exception
        # types regardless of what the provider throws internally.
        raise RuntimeError(f"LLM API call failed: {str(e)}") from e

# ---------------------------------------------------------------------------
# Code review — structured output
# ---------------------------------------------------------------------------

# System prompt that instructs the LLM to return strictly formatted JSON.
# This is the most important prompt in the entire project.
# Every field maps directly to the ReviewIssue Pydantic model in models.py.
CODE_REVIEW_SYSTEM_PROMPT = """
You are an expert Python code reviewer specializing in security vulnerabilities and code quality.

You will receive code snippets that have already been flagged by static analysis tools (bandit and pylint).
Your job is to explain each flagged issue clearly and suggest a concrete fix.

You MUST respond with a valid JSON array and nothing else.
No preamble, no explanation outside the JSON, no markdown code fences.

Each object in the array must have exactly these fields:
{
    "line_number": <integer — the exact line number from the snippet>,
    "severity": <string — exactly one of: "critical", "warning", "suggestion">,
    "issue_title": <string — short label, e.g. "SQL Injection Vulnerability">,
    "explanation": <string — plain-English explanation of why this is a problem>,
    "fix_suggestion": <string — concrete, actionable fix for the developer>
}

Severity guide:
- critical: security vulnerability, data loss risk, or code that will crash in production
- warning: bad practice that will likely cause bugs or maintenance problems
- suggestion: improvement that would make the code cleaner or more robust

If you find no issues in the snippet, return an empty array: []
""".strip()

def _build_review_prompt(
    filename: str,
    static_issues: list[dict],
    patch: str,
) -> str:
    """
    Builds the user prompt for the code review LLM call.

    Sends only flagged lines with surrounding context — not the full file.
    This is the core cost-optimization technique of the hybrid pipeline.

    Args:
        filename:      The name of the file being reviewed.
        static_issues: Normalized issues from static_analyzer.analyze_files().
        patch:         The full raw diff patch string for this file.

    Returns:
        A formatted prompt string ready to send to the LLM.
    """
    # Extract surrounding context lines from the patch for each flagged line
    patch_lines = patch.splitlines()
    flagged_line_numbers = {issue["line"] for issue in static_issues}

    # Collect lines within 3 lines of any flagged line
    context_line_indices: set[int] = set()
    for line_no in flagged_line_numbers:
        for offset in range(-3, 4):  # -3 to +3 inclusive
            idx = line_no + offset - 1  # convert to 0-indexed
            if 0 <= idx < len(patch_lines):
                context_line_indices.add(idx)

    # Build the context snippet preserving line numbers
    context_lines = []
    for idx in sorted(context_line_indices):
        line_no = idx + 1
        marker = ">>>" if line_no in flagged_line_numbers else "   "
        context_lines.append(f"{marker} Line {line_no:3}: {patch_lines[idx]}")

    context_snippet = "\n".join(context_lines)

    # Summarize what static analysis found
    static_summary = "\n".join(
        f"- Line {issue['line']} [{issue['source']}:{issue['rule_id']}]: {issue['message']}"
        for issue in static_issues
    )

    return (
        f"File: {filename}\n\n"
        f"Static analysis flagged these issues:\n{static_summary}\n\n"
        f"Relevant code (>>> marks flagged lines):\n{context_snippet}\n\n"
        f"For each flagged issue, return a JSON object as specified. "
        f"Use the exact line numbers shown above."
    )

def _extract_json(raw: str) -> list[dict]:
    """
    Extracts a JSON array from the LLM response.

    Handles cases where the model wraps the JSON in markdown code fences
    despite being instructed not to. Falls back to regex extraction if
    direct parsing fails.

    Args:
        raw: Raw string response from the LLM.

    Returns:
        A list of issue dicts.

    Raises:
        ValueError: If no valid JSON array can be extracted after all attempts.
    """
    # Attempt 1 — direct parse (ideal case, model followed instructions)
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Attempt 2 — strip markdown code fences and retry
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Attempt 3 — find the first [...] block in the response
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON array from LLM response: {raw[:200]}")

def review_code_with_llm(
    filename: str,
    static_issues: list[dict],
    patch: str,
    max_retries: int = 3,
) -> list[dict]:
    """
    Sends flagged code snippets to the LLM and returns structured review issues.

    This is the only function main.py calls for code review.
    ask_llm() is used by the /ask diagnostic endpoint only.

    Args:
        filename:      The file being reviewed.
        static_issues: Issues from static_analyzer.analyze_files() for this file.
        patch:         Raw unified diff string for this file from GitHub.
        max_retries:   Number of attempts if JSON parsing fails.

    Returns:
        List of issue dicts matching the ReviewIssue schema in models.py.
        Returns empty list if no issues found or LLM repeatedly fails.

    Raises:
        RuntimeError: If all retry attempts fail due to API errors.
    """
    if not static_issues:
        return []

    prompt = _build_review_prompt(filename, static_issues, patch)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            raw = ask_llm(prompt=prompt, system_prompt=CODE_REVIEW_SYSTEM_PROMPT)
            issues = _extract_json(raw)
            return issues

        except ValueError as e:
            # JSON parsing failed — feed the error back on next attempt
            last_error = e
            if attempt < max_retries:
                prompt += (
                    f"\n\nYour previous response could not be parsed as JSON. "
                    f"Error: {e}. Please return only a valid JSON array."
                )

        except RuntimeError:
            raise

    raise RuntimeError(
        f"LLM failed to return valid JSON after {max_retries} attempts. "
        f"Last error: {last_error}"
    )