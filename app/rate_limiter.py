"""
app/rate_limiter.py

Rate limiting configuration using slowapi.

slowapi is a port of the popular Flask-Limiter library to FastAPI/Starlette.
It tracks request counts per client and rejects requests that exceed the
configured limit, returning 429 Too Many Responses.

This file only configures the Limiter instance. It is wired into the
FastAPI app (state, exception handler, middleware) in main.py, and applied
per-route using the @limiter.limit(...) decorator.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# get_remote_address identifies clients by their IP address.
# This means rate limits are per-IP, not per-API-key — two different API
# keys from the same IP would share a limit. For a portfolio-scale project
# this is the standard, simplest approach. A production system handling
# many users behind the same NAT/proxy would key on the API key instead.
limiter = Limiter(key_func=get_remote_address)