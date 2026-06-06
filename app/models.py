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
from typing import Literal


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

class ReviewIssue(BaseModel):
    """
    A single code issue identified by the hybrid analysis pipeline.
    Produced by the LLM after receiving statically-flagged code snippets.
    """

    line_number: int = Field(
        description="Line number in the original file where the issue occurs."
    )
    severity: Literal["critical", "warning", "suggestion"] = Field(
        description="Issue severity. critical = must fix, warning = should fix, suggestion = consider fixing."
    )
    issue_title: str = Field(
        description="Short label for the issue. E.g. 'SQL Injection Vulnerability'."
    )
    explanation: str = Field(
        description="Plain-English explanation of why this is a problem."
    )
    fix_suggestion: str = Field(
        description="Concrete, actionable recommendation for the developer."
    )

class ReviewResponse(BaseModel):
    """
    Response body for the POST /review endpoint.
    Contains structured per-issue results instead of a plain text review.
    """

    pr_url: str = Field(description="The PR URL that was reviewed.")
    metadata: dict = Field(description="PR metadata: title, author, state, branches.")
    issues: list[ReviewIssue] = Field(
        description="List of issues found, ordered by severity."
    )
    files_analyzed: int = Field(description="Number of Python files analyzed.")
    total_added_lines: int = Field(description="Total added lines across all analyzed files.")
    static_issues_found: int = Field(
        description="Number of issues flagged by static analysis before LLM call."
    )
    llm_called: bool = Field(
        description="Whether the LLM was invoked. False means zero static issues were found."
    )
    
class HealthResponse(BaseModel):
    """Response body for the GET /health endpoint."""

    status: str
