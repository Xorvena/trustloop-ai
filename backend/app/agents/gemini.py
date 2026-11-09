"""Thin Gemini wrapper (official `google-genai` SDK).

Security design: Gemini is used ONLY for structured output (no tools / function calling are registered),
so even a successful prompt injection cannot trigger an action. Output is always re-validated with
Pydantic and never directly applied to stored permissions or payment operations.

Error handling: failures are classified into a short, safe `code` + message that callers can show to users.
The raw exception text is logged server-side only after redacting API-key-like strings.
"""
import contextvars
import logging
import re
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

log = logging.getLogger("trustloop.gemini")
T = TypeVar("T", bound=BaseModel)

_KEY_PATTERNS = [re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), re.compile(r"(?i)(api[_-]?key|key)=([^&\s\"']+)"),
                 re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{10,}")]


class GeminiUnavailable(Exception):
    """Not configured or upstream failure. `code` is machine-readable; str(exc) is safe to show to users."""
    def __init__(self, message: str, code: str = "unavailable"):
        super().__init__(message)
        self.code = code


class GeminiBadOutput(Exception):
    """Model output failed schema validation."""
    code = "bad_output"


def redact(text: str) -> str:
    """Remove anything that looks like an API key or bearer token, plus the configured key itself."""
    key = get_settings().gemini_api_key
    if key:
        text = text.replace(key, "[REDACTED]")
    for p in _KEY_PATTERNS:
        text = p.sub(lambda m: "[REDACTED]" if m.re.groups < 2 else f"{m.group(1)}=[REDACTED]", text)
    return text


def classify(exc: Exception) -> tuple[str, str]:
    """Map an SDK/network exception to (code, safe user-facing message). Never includes raw exception text."""
    model = get_settings().gemini_model
    status = getattr(exc, "code", None)
    raw = redact(str(exc)).lower()
    name = type(exc).__name__
    if "api key not valid" in raw or "api_key_invalid" in raw or status in (401,):
        return "invalid_api_key", "Gemini rejected the API key. Check GEMINI_API_KEY."
    if status == 403:
        return "permission_denied", "Gemini denied access (key restrictions, region, or billing). Check your key's permissions."
    if status == 404 or "not found" in raw and "model" in raw:
        return "model_not_found", f"Model '{model}' was not found or is not available to this key. Set GEMINI_MODEL to a current model from the Gemini models page."
    if status == 429 or "resource_exhausted" in raw or "quota" in raw:
        return "rate_limited", "Gemini rate limit or quota reached. Try again shortly or check your quota."
    if isinstance(status, int) and status >= 500:
        return "upstream_error", f"Gemini service error (HTTP {status}). Try again later."
    if status == 400:
        return "bad_request", "Gemini rejected the request (HTTP 400). The model may not support structured output."
    if any(s in name for s in ("Timeout", "Connect", "Network", "Transport")):
        return "network_error", "Could not reach the Gemini API (network or timeout)."
    detail = redact(str(exc)).strip().replace("\n", " ")[:200]
    return "unknown_error", f"Gemini request failed ({name}{': ' + detail if detail else ''})."


def is_configured() -> bool:
    return bool(get_settings().gemini_api_key)


_clients: dict[tuple, object] = {}
_sleep = time.sleep                       # patched in tests
_down_until = 0.0                         # simple circuit breaker (per process)
_model_down: dict[str, float] = {}        # model -> skip-until timestamp (a failing PRIMARY model is skipped for a while)
_last_failure: dict[str, tuple[str, str, float]] = {}   # model -> (code, safe message, timestamp)
_used: contextvars.ContextVar[tuple[str | None, bool]] = contextvars.ContextVar("gemini_used", default=(None, False))
TRANSIENT_CODES = {"upstream_error", "network_error"}


def reset_state() -> None:
    global _down_until
    _down_until = 0.0
    _model_down.clear()
    _last_failure.clear()
    _clients.clear()
    _used.set((None, False))


def used_model() -> tuple[str | None, bool]:
    """(model that produced the LAST successful response in this request context, whether it was the fallback model)."""
    return _used.get()


def _client():
    """Return a LONG-LIVED SDK client.

    Do not create a temporary client inline (`genai.Client(...).models.generate_content(...)`): the SDK closes its HTTP
    connection in `Client.__del__`, so a temporary is garbage-collected mid-call and the request fails with
    "RuntimeError: Cannot send a request, as the client has been closed". We cache one client per config and callers
    must keep a local reference while using it.
    """
    from google import genai  # imported lazily so the app starts without credentials
    from google.genai import types
    s = get_settings()
    cache_key = (s.gemini_api_key, s.gemini_base_url, s.gemini_timeout_seconds)
    if cache_key not in _clients:
        opts = types.HttpOptions(timeout=int(s.gemini_timeout_seconds * 1000), **({"base_url": s.gemini_base_url} if s.gemini_base_url else {}))
        _clients[cache_key] = genai.Client(api_key=s.gemini_api_key, http_options=opts)
    return _clients[cache_key]


def _config(system: str, schema, with_thinking: bool):
    """Generation config. We deliberately do NOT set temperature: Google recommends the default (1.0) for Gemini 3 models and warns that
    lower values can cause looping/degraded performance. Output is schema-validated anyway."""
    from google.genai import types
    s = get_settings()
    kw: dict = dict(system_instruction=system, response_mime_type="application/json", response_schema=schema)
    if with_thinking and s.gemini_thinking_level:
        kw["thinking_config"] = types.ThinkingConfig(thinking_level=s.gemini_thinking_level.upper())
    return types.GenerateContentConfig(**kw)


def generate_structured(system: str, user: str, schema: type[T], purpose: str = "generic") -> T:
    """Structured generation with bounded retries, a lighter fallback model, and a circuit breaker. Every failure is classified and
    logged (keys redacted); callers get a GeminiUnavailable with a safe message. `used_model()` says which model answered."""
    global _down_until
    s = get_settings()
    if not s.gemini_api_key:
        raise GeminiUnavailable("GEMINI_API_KEY is not configured.", "not_configured")
    if time.time() < _down_until:
        raise GeminiUnavailable("Gemini was unavailable a moment ago, so it was skipped to keep the app responsive. It will be retried shortly.", "recently_unavailable")
    deadline = time.time() + s.gemini_total_budget_seconds
    models = [(s.gemini_model, 1 + max(0, s.gemini_retries), False)]
    if s.gemini_fallback_model and s.gemini_fallback_model != s.gemini_model:
        models.append((s.gemini_fallback_model, 2, True))
    if len(models) > 1 and _model_down.get(s.gemini_model, 0) > time.time():
        models = models[1:]                      # the primary failed recently: go straight to the fallback (keeps searches fast)
    last: tuple[str, str] = ("unavailable", "Gemini is unavailable.")
    client = _client()  # keep a reference for the duration of the call (see _client docstring)
    for model, attempts, is_fallback in models:
        thinking = True
        i = 0
        while i < attempts:
            i += 1
            if time.time() > deadline:
                last = ("network_error", "Gemini did not answer within the time budget.")
                break
            try:
                resp = client.models.generate_content(model=model, contents=user, config=_config(system, schema, thinking))
            except Exception as exc:  # network, quota, bad model name, ...
                code, msg = classify(exc)
                log.warning("Gemini call failed purpose=%s model=%s attempt=%d/%d code=%s type=%s detail=%s", purpose, model, i, attempts, code,
                            type(exc).__name__, redact(str(exc))[:500])
                last = (code, msg)
                if code == "bad_request" and thinking and s.gemini_thinking_level:
                    thinking, i = False, i - 1          # the model rejected our thinking level: retry once without it
                    continue
                if code in ("invalid_api_key", "permission_denied"):
                    raise GeminiUnavailable(msg, code) from None   # no retry/fallback can fix a key problem
                if code in TRANSIENT_CODES and i < attempts:
                    _sleep(min(0.7 * (2 ** (i - 1)), 3.0))         # 0.7s, 1.4s ...
                    continue
                break                                              # quota, wrong model name, other: try the next model
            try:
                out = schema.model_validate_json(resp.text or "")
            except (ValidationError, ValueError) as exc:
                log.warning("Gemini output failed validation purpose=%s model=%s detail=%s", purpose, model, redact(str(exc))[:300])
                last = ("bad_output", "Gemini returned output that did not match the expected schema.")
                break
            if not is_fallback:
                _model_down.pop(model, None)
                _last_failure.pop(model, None)
            _used.set((model, is_fallback))
            if is_fallback:
                log.warning("Gemini fallback model used purpose=%s primary=%s fallback=%s", purpose, s.gemini_model, model)
            return out
        # this model exhausted its attempts without success
        if last[0] != "bad_output":
            _last_failure[model] = (last[0], last[1], time.time())
            if not is_fallback and len(models) > 1:
                _model_down[model] = time.time() + s.gemini_model_cooldown_seconds
                log.warning("Gemini primary model %s is failing (%s); skipping it for %ss", model, last[0], int(s.gemini_model_cooldown_seconds))
    code, msg = last
    if code in TRANSIENT_CODES:
        _down_until = time.time() + s.gemini_circuit_seconds
    if code == "bad_output":
        raise GeminiBadOutput(msg) from None
    tried = " then ".join(m for m, _, _ in models)
    raise GeminiUnavailable(f"{msg} (models tried: {tried})" if len(models) > 1 else msg, code) from None


def status() -> dict:
    """Why the fallback model may be in use: the primary's last failure, and whether it is currently being skipped."""
    s = get_settings()
    now = time.time()
    lf = _last_failure.get(s.gemini_model)
    return {"primary_model": s.gemini_model, "fallback_model": s.gemini_fallback_model or None,
            "primary_cooling_down_seconds": max(0, int(_model_down.get(s.gemini_model, 0) - now)),
            "primary_last_failure": None if not lf else {"code": lf[0], "message": lf[1], "seconds_ago": int(now - lf[2])}}


def probe(models: list[str]) -> list[dict]:
    """Diagnostics: send ONE tiny request per model, plain and with structured output, and report latency + classified errors.
    Does not touch the circuit breaker or cooldowns."""
    from google.genai import types
    from pydantic import BaseModel as _BM

    class _Ping(_BM):
        ok: bool

    s = get_settings()
    if not s.gemini_api_key:
        return [{"model": m, "configured": False, "code": "not_configured", "message": "GEMINI_API_KEY is not configured."} for m in models]
    client = _client()
    out = []
    for m in models:
        row: dict = {"model": m}
        for kind, cfg in (("plain", types.GenerateContentConfig(max_output_tokens=20)),
                          ("structured", types.GenerateContentConfig(response_mime_type="application/json", response_schema=_Ping, max_output_tokens=50))):
            t0 = time.time()
            try:
                r = client.models.generate_content(model=m, contents="Reply with the single word OK." if kind == "plain" else "Return ok=true.", config=cfg)
                row[kind] = {"ok": True, "latency_ms": int((time.time() - t0) * 1000), "reply": (r.text or "")[:40]}
            except Exception as exc:
                code, msg = classify(exc)
                log.warning("Gemini probe failed model=%s kind=%s code=%s type=%s detail=%s", m, kind, code, type(exc).__name__, redact(str(exc))[:300])
                row[kind] = {"ok": False, "latency_ms": int((time.time() - t0) * 1000), "code": code, "message": msg}
        out.append(row)
    return out


def check_model() -> dict:
    """Ask the Gemini API whether the configured model exists for this key (no generation, no cost)."""
    s = get_settings()
    if not s.gemini_api_key:
        return {"configured": False, "ok": False, "model": s.gemini_model, "code": "not_configured",
                "message": "GEMINI_API_KEY is not configured."}
    try:
        client = _client()
        info = client.models.get(model=s.gemini_model)
        return {"configured": True, "ok": True, "model": s.gemini_model, "resolved_name": getattr(info, "name", None),
                "code": None, "message": "Model is available to this API key."}
    except Exception as exc:
        code, msg = classify(exc)
        log.warning("Gemini model check failed model=%s code=%s type=%s detail=%s", s.gemini_model, code, type(exc).__name__, redact(str(exc))[:500])
        return {"configured": True, "ok": False, "model": s.gemini_model, "code": code, "message": msg}
