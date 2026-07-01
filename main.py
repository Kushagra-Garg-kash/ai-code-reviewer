"""
main.py

FastAPI application entry point.
All route definitions live here.
All business logic lives in app/ modules — this file only handles HTTP concerns:
routing, request parsing, error mapping to HTTP status codes.

"""

from fastapi import FastAPI, HTTPException, Request, Depends
from contextlib import asynccontextmanager
from app.database import init_db, save_review, get_recent_reviews
from app.llm_client import ask_llm, review_code_with_llm
from app.models import AskRequest, AskResponse, HealthResponse, ReviewRequest, ReviewResponse, ReviewHistoryItem
import requests as http_requests
from app.github_client import get_python_diffs_from_pr
from app.static_analyzer import analyze_files
from app.auth import verify_api_key
from app.rate_limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="AI Code Reviewer",
    description=(
        "Automated GitHub PR review using static analysis + LLM reasoning. "
    ),
    version="0.1.0",
    docs_url="/docs",     
    redoc_url="/redoc", 
    lifespan=lifespan,   
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
def ask_endpoint(request: AskRequest, _: None = Depends(verify_api_key)) -> AskResponse:
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
@limiter.limit("10/minute")
def review_pr(request: Request, review_request: ReviewRequest, _: None = Depends(verify_api_key)) -> ReviewResponse:
    """
    Accepts a GitHub PR URL and returns a structured AI code review.

    Pipeline:
    1. Fetch PR diff from GitHub (Python files only).
    2. Run static analysis (bandit + pylint) on added lines.
    3. If zero issues found — return immediately, no LLM call.
    4. For each file with issues — send flagged lines + context to LLM.
    5. Collect structured JSON issues across all files.
    6. Return unified ReviewResponse.
    """
    # Step 1 — Fetch diff from GitHub
    try:
        pr_data = get_python_diffs_from_pr(review_request.pr_url)
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

    # Step 3 — Run static analysis on all files

    static_results = analyze_files(pr_data["files"])

    # Count total static issues across all files
    total_static_issues = sum(len(issues) for issues in static_results.values())

    # Step 4 — If no issues found, return early — zero LLM cost
    total_added = sum(len(f["added_lines"]) for f in pr_data["files"])

    if total_static_issues == 0:
        save_review(
            pr_url=review_request.pr_url,
            issue_count=0,
            critical_count=0,
            warning_count=0,
        )
        return ReviewResponse(
            pr_url=review_request.pr_url,
            metadata=pr_data["metadata"],
            issues=[],
            files_analyzed=len(pr_data["files"]),
            total_added_lines=total_added,
            static_issues_found=0,
            llm_called=False,
        )

    # Step 5 — Call LLM only for files that have static issues
    all_issues = []

    for file in pr_data["files"]:
        filename = file["filename"]
        static_issues = static_results.get(filename, [])

        if not static_issues:
            continue

        try:
            llm_issues = review_code_with_llm(
                filename=filename,
                static_issues=static_issues,
                patch=file["patch"],
            )
            all_issues.extend(llm_issues)

        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))

    # Step 6 — Sort by severity (critical first) and return
    severity_order = {"critical": 0, "warning": 1, "suggestion": 2}
    all_issues.sort(key=lambda x: severity_order.get(x.get("severity", "suggestion"), 2))

    critical_count = sum(1 for i in all_issues if i.get("severity") == "critical")
    warning_count = sum(1 for i in all_issues if i.get("severity") == "warning")

    save_review(
        pr_url=review_request.pr_url,
        issue_count=len(all_issues),
        critical_count=critical_count,
        warning_count=warning_count,
    )

    return ReviewResponse(
        pr_url=review_request.pr_url,
        metadata=pr_data["metadata"],
        issues=all_issues,
        files_analyzed=len(pr_data["files"]),
        total_added_lines=total_added,
        static_issues_found=total_static_issues,
        llm_called=True,
    )

@app.get("/reviews", response_model=list[ReviewHistoryItem], tags=["Review"])
def list_reviews(limit: int = 10) -> list[dict]:
    """
    Return the most recent review history entries, newest first.

    Used by the Streamlit sidebar to display recent activity without
    touching the database directly — frontend stays a pure presentation
    layer, all storage access goes through this API.
    """
    return get_recent_reviews(limit=limit)