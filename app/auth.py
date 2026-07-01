"""
app/auth.py

API key authentication for protected endpoints.

Uses FastAPI's dependency injection system: routes that need protection
declare a dependency on verify_api_key, which runs before the route
handler executes. If the key is missing or wrong, this raises an
HTTPException before any business logic (and any LLM cost) is triggered.
"""

import os
from fastapi import Header, HTTPException
from dotenv import load_dotenv

load_dotenv()

APP_API_KEY = os.getenv("APP_API_KEY")


def verify_api_key(x_api_key: str = Header(...)) -> None:
    """
    FastAPI dependency that validates the X-API-Key request header.

    FastAPI automatically maps the Header(...) parameter to the
    'X-API-Key' HTTP header (it converts the Python parameter name
    x_api_key to the header name by replacing underscores with hyphens
    and capitalizing — this is FastAPI's standard convention, not
    something we configure manually).

    Args:
        x_api_key: The value of the X-API-Key header, injected by FastAPI.

    Raises:
        HTTPException: 401 if the header is missing or does not match
            the configured APP_API_KEY.
    """
    if not APP_API_KEY:
        # Misconfiguration on our end — the server has no key configured.
        # 500, not 401, because this is our bug, not the caller's.
        raise HTTPException(
            status_code=500,
            detail="Server is missing APP_API_KEY configuration.",
        )

    if x_api_key != APP_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
        )