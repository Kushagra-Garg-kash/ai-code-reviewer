"""
github_client.py

Responsible for all communication with the GitHub REST API.
Fetches PR metadata and raw unified diffs for a given pull request URL.
"""

import re
import requests
from dotenv import load_dotenv
import os

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# GitHub API base URL
GITHUB_API_BASE = "https://api.github.com"

# Request headers — token auth + ask GitHub to return diff format
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """
    Parses a GitHub PR URL and extracts owner, repo name, and PR number.

    Args:
        pr_url: Full GitHub PR URL.
                Example: https://github.com/owner/repo/pull/42

    Returns:
        A tuple of (owner, repo, pr_number).

    Raises:
        ValueError: If the URL does not match the expected GitHub PR format.
    """
    pattern = r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.match(pattern, pr_url.strip())

    if not match:
        raise ValueError(
            f"Invalid GitHub PR URL: '{pr_url}'. "
            "Expected format: https://github.com/owner/repo/pull/123"
        )

    owner = match.group(1)
    repo = match.group(2)
    pr_number = int(match.group(3))

    return owner, repo, pr_number


def fetch_pr_metadata(owner: str, repo: str, pr_number: int) -> dict:
    """
    Fetches basic metadata about a pull request.

    Args:
        owner: Repository owner (GitHub username or org name).
        repo: Repository name.
        pr_number: Pull request number.

    Returns:
        A dict containing PR title, author, state, and base/head branch info.

    Raises:
        requests.HTTPError: If the GitHub API returns a non-2xx response.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()

    data = response.json()

    return {
        "title": data["title"],
        "author": data["user"]["login"],
        "state": data["state"],
        "base_branch": data["base"]["ref"],
        "head_branch": data["head"]["ref"],
        "pr_number": pr_number,
        "repo": f"{owner}/{repo}",
    }


def fetch_pr_files(owner: str, repo: str, pr_number: int) -> list[dict]:
    """
    Fetches the list of files changed in a pull request, including their diffs.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pr_number: Pull request number.

    Returns:
        A list of dicts, each containing:
            - filename: str
            - status: str ('added', 'modified', 'removed')
            - patch: str — the raw unified diff for that file (may be absent
                     for binary files or files with no textual changes)

    Raises:
        requests.HTTPError: If the GitHub API returns a non-2xx response.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files"
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()

    files = response.json()

    result = []
    for f in files:
        result.append({
            "filename": f["filename"],
            "status": f["status"],
            # 'patch' is absent for binary files — use .get() to handle safely
            "patch": f.get("patch", ""),
        })

    return result


def extract_added_lines(patch: str) -> list[tuple[int, str]]:
    """
    Parses a unified diff patch and extracts only the lines that were ADDED.

    In unified diff format:
        Lines starting with '+' are additions (what we want to analyze).
        Lines starting with '-' are deletions (leaving the codebase, skip).
        Lines starting with ' ' are context lines (unchanged).
        Lines starting with '@@' are hunk headers showing line numbers.

    Args:
        patch: The raw unified diff string from GitHub's API.

    Returns:
        A list of (line_number, line_content) tuples for added lines only.
        line_number refers to the line number in the NEW version of the file.
    """
    added_lines = []
    current_line_number = 0

    for line in patch.splitlines():
        # Hunk header — tells us where in the new file this chunk starts
        # Format: @@ -old_start,old_count +new_start,new_count @@
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            if match:
                # Next line will be at this line number in the new file
                current_line_number = int(match.group(1)) - 1
            continue

        if line.startswith("+") and not line.startswith("+++"):
            # This is an added line — strip the leading '+' to get actual code
            current_line_number += 1
            added_lines.append((current_line_number, line[1:]))

        elif line.startswith("-"):
            # Removed line — does NOT advance the new file's line counter
            continue

        else:
            # Context line (unchanged) — advances line counter
            current_line_number += 1

    return added_lines


def get_python_diffs_from_pr(pr_url: str) -> dict:
    """
    Master function — given a PR URL, returns all the data needed for analysis.

    Filters to Python files only. Extracts added lines from each file's diff.

    Args:
        pr_url: Full GitHub PR URL.

    Returns:
        A dict with:
            - metadata: dict with PR title, author, state, etc.
            - files: list of dicts, each with:
                - filename: str
                - patch: str (full raw diff)
                - added_lines: list of (line_number, line_content) tuples

    Raises:
        ValueError: If the PR URL is invalid.
        requests.HTTPError: If any GitHub API call fails.
    """
    owner, repo, pr_number = parse_pr_url(pr_url)

    metadata = fetch_pr_metadata(owner, repo, pr_number)
    all_files = fetch_pr_files(owner, repo, pr_number)

    # Filter to Python files only — other languages handled in future extensions
    python_files = [f for f in all_files if f["filename"].endswith(".py")]

    result_files = []
    for f in python_files:
        added = extract_added_lines(f["patch"]) if f["patch"] else []
        result_files.append({
            "filename": f["filename"],
            "patch": f["patch"],
            "added_lines": added,
        })

    return {
        "metadata": metadata,
        "files": result_files,
    }