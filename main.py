"""
main.py

FastAPI application entry point.
All route definitions live here.
All business logic lives in app/ modules — this file only handles HTTP concerns:
routing, request parsing, error mapping to HTTP status codes.

Run locally with:
    uvicorn main:app --reload
"""

from fastapi import FastAPI, HTTPException
from app.llm_client import ask_llm
from app.models import AskRequest, AskResponse, HealthResponse, ReviewRequest, ReviewResponse
import requests as http_requests
from app.github_client import get_python_diffs_from_pr

# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Code Reviewer",
    description=(
        "Automated GitHub PR review using static analysis + LLM reasoning. "
        "Built as a placement portfolio project."
    ),
    version="0.1.0",
    docs_url="/docs",      # Swagger UI — open this in browser to test manually
    redoc_url="/redoc",    # Alternative API docs UI
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health_check() -> HealthResponse:
    """
    Quick liveness check.
    Used by deployment platforms (Render) to verify the container is running.
    Returns 200 if the server is up.
    """
    return HealthResponse(status="ok")


@app.post("/ask", response_model=AskResponse, tags=["LLM"])
def ask_endpoint(request: AskRequest) -> AskResponse:
    """
    Send a prompt to the LLM and return its response.

    This is a diagnostic and development endpoint used to verify the LLM
    integration is working correctly. In the final product, this logic will
    be embedded inside the POST /review endpoint with a structured
    code-review-specific prompt.

    Returns 502 if the LLM provider fails (upstream error).
    Returns 500 if the LLM returns an empty/malformed response.
    Returns 422 automatically if request validation fails (Pydantic handles this).
    """
    try:
        result = ask_llm(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
        )
        return AskResponse(response=result)

    except RuntimeError as e:
        # The LLM provider itself failed (auth error, rate limit, network issue).
        # 502 = Bad Gateway: our server is up, but an upstream dependency failed.
        raise HTTPException(status_code=502, detail=str(e))

    except ValueError as e:
        # The provider responded but returned unusable content.
        # 500 = our system couldn't produce a valid response.
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/review", response_model=ReviewResponse, tags=["Review"])
def review_pr(request: ReviewRequest) -> ReviewResponse:
    """
    Accepts a GitHub PR URL and returns an LLM-generated code review.

    Day 5 prototype behaviour:
    - Fetches only Python files from the PR diff.
    - Passes all added lines to the LLM as a single prompt (no chunking yet).
    - Returns the raw LLM response as a plain string.

    Week 2 will replace this with static analysis pre-filtering,
    structured JSON output, and token chunking for large PRs.
    """
    # Step 1 — Fetch diff from GitHub
    try:
        pr_data = get_python_diffs_from_pr(request.pr_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except http_requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {str(e)}")

    # Step 2 — Bail early if no Python files were changed
    if not pr_data["files"]:
        raise HTTPException(
            status_code=422,
            detail="No Python files found in this PR. Only Python is supported in v0.1."
        )

    # Step 3 — Collect all added lines across all Python files
    all_added_lines = []
    for file in pr_data["files"]:
        if file["added_lines"]:
            all_added_lines.append(f"\n### File: {file['filename']}")
            for line_no, content in file["added_lines"]:
                all_added_lines.append(f"Line {line_no}: {content}")

    diff_text = "\n".join(all_added_lines)

    # Step 4 — Basic review prompt (replaced with structured prompt in Week 2)
    system_prompt = (
        "You are an expert Python code reviewer. "
        "You will be given lines of code added in a GitHub pull request. "
        "Your job is to identify bugs, security issues, and code quality problems. "
        "Be specific — reference line numbers. Be concise and direct."
    )

    user_prompt = (
        f"Review the following code changes from a GitHub pull request.\n\n"
        f"{diff_text}\n\n"
        f"Identify any bugs, security vulnerabilities, or code quality issues. "
        f"For each issue, state the line number, what the problem is, and how to fix it."
    )

    # Step 5 — Call the LLM
    try:
        review_text = ask_llm(prompt=user_prompt, system_prompt=system_prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Step 6 — Return structured response
    total_added = sum(len(f["added_lines"]) for f in pr_data["files"])

    return ReviewResponse(
        pr_url=request.pr_url,
        metadata=pr_data["metadata"],
        review=review_text,
        files_analyzed=len(pr_data["files"]),
        total_added_lines=total_added,
    )