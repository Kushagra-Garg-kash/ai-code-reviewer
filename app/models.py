"""
app/models.py

Pydantic models for all API request and response schemas.
Centralizing models here means they can be imported by both main.py
and any future modules without circular imports.

Pydantic v2 handles:
- Type validation automatically (wrong type → 422 response)
- Field constraints (min_length, max_length)
- Auto-generated OpenAPI schema in /docs
"""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Request body for the POST /ask endpoint."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="The prompt to send to the LLM.",
        examples=["What is SQL injection and why is it dangerous?"],
    )
    system_prompt: str = Field(
        default="You are a helpful assistant.",
        max_length=1000,
        description="Optional system instruction that defines the model's role.",
    )


class AskResponse(BaseModel):
    """Response body for the POST /ask endpoint."""

    response: str = Field(description="The LLM's plain-text response.")
    model_used: str = Field(
        default="llama-3.1-8b-instant",
        description="The model that generated this response.",
    )

class ReviewRequest(BaseModel):
    """Request body for the POST /review endpoint."""

    pr_url: str = Field(
        ...,
        description="Full GitHub pull request URL.",
        examples=["https://github.com/psf/requests/pull/6710"],
    )

class ReviewResponse(BaseModel):
    """Response body for the POST /review endpoint."""

    pr_url: str = Field(description="The PR URL that was reviewed.")
    metadata: dict = Field(description="PR metadata: title, author, state, branches.")
    review: str = Field(description="LLM-generated plain-text code review.")
    files_analyzed: int = Field(description="Number of Python files analyzed.")
    total_added_lines: int = Field(description="Total added lines across all analyzed files.")

class HealthResponse(BaseModel):
    """Response body for the GET /health endpoint."""

    status: str
