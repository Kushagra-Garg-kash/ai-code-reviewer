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
from app.models import AskRequest, AskResponse, HealthResponse

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
