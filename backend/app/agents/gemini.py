"""Thin Gemini wrapper (official `google-genai` SDK).

Security design: Gemini is used ONLY for structured output (no tools / function calling are registered),
so even a successful prompt injection cannot trigger an action. Output is always re-validated with
Pydantic and never directly applied to stored permissions or payment operations.
"""
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)


class GeminiUnavailable(Exception):
    """Not configured or upstream failure."""


class GeminiBadOutput(Exception):
    """Model output failed schema validation."""


def is_configured() -> bool:
    return bool(get_settings().gemini_api_key)


def _client():
    from google import genai  # imported lazily so the app starts without credentials
    return genai.Client(api_key=get_settings().gemini_api_key)


def generate_structured(system: str, user: str, schema: type[T]) -> T:
    s = get_settings()
    if not s.gemini_api_key:
        raise GeminiUnavailable("GEMINI_API_KEY is not configured.")
    from google.genai import types
    try:
        resp = _client().models.generate_content(
            model=s.gemini_model,
            contents=user,
            config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                                               response_schema=schema, temperature=0.0),
        )
    except Exception as exc:  # network, quota, bad model name, ...
        raise GeminiUnavailable(f"Gemini request failed: {type(exc).__name__}: {exc}") from exc
    try:
        return schema.model_validate_json(resp.text or "")
    except (ValidationError, ValueError) as exc:
        raise GeminiBadOutput(f"Gemini output failed validation: {exc}") from exc
