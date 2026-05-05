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
        default="llama3-8b-8192",
        description="The model that generated this response.",
    )


class HealthResponse(BaseModel):
    """Response body for the GET /health endpoint."""

    status: str
