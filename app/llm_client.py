"""
app/llm_client.py

Handles all communication with the LLM provider (Groq).
Abstracted behind a simple ask_llm() function so the rest of the codebase
is completely decoupled from the provider. Switching from Groq to OpenAI
requires changes only in this file.
"""

import os
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
