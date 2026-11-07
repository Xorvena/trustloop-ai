"""Gemini integration behaviour with a MOCKED client (not a live-integration test): failures must be visible, safe, and
never presented as Gemini output."""
import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from app.agents import gemini
from app.agents.shopping import EXPLAIN_SYSTEM, INTENT_SYSTEM
from app.core.config import Settings, get_settings

FAKE_KEY = "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKE1234567"
MODEL = "gemini-3.8-flash"


@pytest.fixture
def gem(monkeypatch):
    """Enable Gemini with a fake key; tests install their own fake client via `install`."""
    s = get_settings()
    old = (s.gemini_api_key, s.gemini_model)
    s.gemini_api_key, s.gemini_model = FAKE_KEY, MODEL

    def install(handler=None, get=None):
        def generate_content(**kw):
            return handler(kw["config"].system_instruction, kw["contents"])
        models = SimpleNamespace(generate_content=generate_content, get=get or (lambda model: SimpleNamespace(name=f"models/{model}")))
        monkeypatch.setattr(gemini, "_client", lambda: SimpleNamespace(models=models))
    yield install
    s.gemini_api_key, s.gemini_model = old


def resp(obj):
    return SimpleNamespace(text=json.dumps(obj))


def raising(exc):
    def h(system, contents):
        raise exc
    return h


def search(ctx, q):
    r = ctx.c.post("/api/products/search", headers=ctx.h, json={"query": q})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- configuration
def test_default_model_is_a_currently_listed_model_not_the_retired_guess(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert Settings(_env_file=None).gemini_model == "gemini-3.8-flash"
    assert Settings(_env_file=None).gemini_model != "gemini-3.5-flash"


# ---------------------------------------------------------------- redaction & classification
def test_redact_removes_keys_and_tokens(gem):
    text = f"GET https://x/v1?key={FAKE_KEY} failed; token {FAKE_KEY}; Bearer abcdefghijklmnop12345; api_key=hunter2secret"
    out = gemini.redact(text)
    assert FAKE_KEY not in out and "hunter2secret" not in out and "abcdefghijklmnop12345" not in out


@pytest.mark.parametrize("exc,code", [
    (errors.ClientError(404, {"error": {"message": f"models/{MODEL} is not found for API version v1beta key={FAKE_KEY}"}}), "model_not_found"),
    (errors.ClientError(400, {"error": {"message": "API key not valid. Please pass a valid API key."}}), "invalid_api_key"),
    (errors.ClientError(403, {"error": {"message": "permission denied"}}), "permission_denied"),
    (errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED quota"}}), "rate_limited"),
    (errors.ServerError(503, {"error": {"message": "overloaded"}}), "upstream_error"),
    (httpx.ConnectTimeout("timed out"), "network_error"),
    (RuntimeError("boom"), "unknown_error"),
])
def test_error_classification_is_safe(gem, exc, code):
    c, msg = gemini.classify(exc)
    assert c == code and FAKE_KEY not in msg and "key=" not in msg.lower()


# ---------------------------------------------------------------- summary: Gemini success vs fallback is always labelled
def test_successful_gemini_summary_is_labelled_gemini(ctx, gem):
    def handler(system, contents):
        if system == INTENT_SYSTEM:
            return resp({"product_type": "laptop", "brand": "ASUS", "model": "Vivobook 16 X1605"})
        return resp({"summary": "The ASUS Vivobook 16 X1605 from TechMart India is the exact model you asked for."})
    gem(handler)
    r = search(ctx, "Asus Vivobook 16 X1605")
    assert r["summary_source"] == "gemini" and r["summary_model"] == MODEL and r["summary_fallback_reason"] is None
    assert r["intent_source"] == "gemini" and r["intent_model"] == MODEL
    assert "exact model" in r["summary"]


@pytest.mark.parametrize("exc,code", [
    (errors.ClientError(404, {"error": {"message": f"models/{MODEL} is not found key={FAKE_KEY}"}}), "model_not_found"),
    (errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED"}}), "rate_limited"),
    (errors.ClientError(400, {"error": {"message": "API key not valid"}}), "invalid_api_key"),
])
def test_gemini_failure_is_visible_labelled_and_leaks_nothing(ctx, gem, caplog, exc, code):
    gem(raising(exc))
    with caplog.at_level(logging.WARNING, logger="trustloop.gemini"):
        r = search(ctx, "Asus Vivobook 16 X1605")
    # never presented as Gemini output
    assert r["summary_source"] == "template" and r["summary_model"] is None
    assert r["summary_fallback_reason"] == code and r["intent_source"] == "heuristic" and r["intent_fallback_reason"] == code
    assert "built-in template" in r["summary_fallback_message"]
    # the search itself still works (rule-based parser), and the failure is logged without secrets
    assert r["status"] == "matches_found"
    blob = json.dumps(r) + caplog.text
    assert FAKE_KEY not in blob and "AIza" not in blob
    assert "Gemini call failed" in caplog.text and code in caplog.text


def test_not_configured_is_labelled_not_gemini(ctx):
    r = search(ctx, "Asus Vivobook 16 X1605")
    assert r["summary_source"] == "template" and r["summary_fallback_reason"] == "not_configured"
    assert r["intent_source"] == "heuristic" and r["intent_fallback_reason"] == "not_configured"


def test_gemini_bad_output_falls_back_visibly(ctx, gem):
    gem(lambda system, contents: SimpleNamespace(text="sure! here you go: not json"))
    r = search(ctx, "Asus Vivobook 16 X1605")
    assert r["summary_source"] == "template" and r["summary_fallback_reason"] == "bad_output"


# ---------------------------------------------------------------- Gemini must not contradict verified results
def test_overclaiming_gemini_summary_is_rejected(ctx, gem):
    def handler(system, contents):
        if system == INTENT_SYSTEM:
            return resp({"product_type": "laptop", "brand": "ASUS", "model": "VivobookX16", "max_budget": 75000})
        return resp({"summary": "Great news! The ASUS Vivobook 16 meets all your requirements."})
    gem(handler)
    r = search(ctx, "Asus VivobookX16 laptop under 75000")
    assert r["status"] == "no_exact_match"
    assert r["summary_source"] == "template" and r["summary_fallback_reason"] == "contradicted_results"
    assert "meets all" not in r["summary"].lower()


def test_gemini_cannot_invent_brand_or_drop_requested_brand(ctx, gem):
    def handler(system, contents):
        if system == INTENT_SYSTEM:  # hallucinated Dell, forgot the user's Asus and model
            return resp({"product_type": "laptop", "brand": "Dell", "model": None})
        return resp({"summary": "No exact match."})
    gem(handler)
    r = search(ctx, "Asus Vivobook 16 X1605 laptop")
    assert r["requirements"]["brand"] == "ASUS" and r["requirements"]["model"] == "Vivobook 16 X1605"
    assert any("Ignored Gemini-suggested brand 'Dell'" in n for n in r["intent_notes"])
    assert any("Added model from the rule-based parser" in n for n in r["intent_notes"])
    assert skus_of(r["matches"]) == ["LT-ASUS-VB16"]


def skus_of(items):
    return [i["product"]["sku"] for i in items]


def test_policy_parse_gemini_failure_falls_back_visibly_not_silently(ctx, gem):
    gem(raising(errors.ClientError(404, {"error": {"message": f"model not found key={FAKE_KEY}"}})))
    r = ctx.c.post("/api/policies/parse", headers=ctx.h, json={"text": "Never spend above 65000. Ask me before any purchase above 25000."})
    j = r.json()
    assert r.status_code == 200 and j["source"] == "heuristic_fallback" and j["draft"]["source"] == "heuristic_fallback"
    assert j["fallback_reason"] == "model_not_found" and "rule-based parser" in j["fallback_message"] and j["model"] is None
    assert j["draft"]["max_budget"] in ("65000", "65000.00") and FAKE_KEY not in r.text


def test_policy_parse_gemini_success_is_labelled_with_model(ctx, gem):
    gem(lambda s, c: resp({"currency": "INR", "max_budget": 65000, "approval_threshold": 25000, "approved_merchants_only": True,
                           "duplicate_purchase_check": True, "approved_merchants": []}))
    j = ctx.c.post("/api/policies/parse", headers=ctx.h, json={"text": "Never spend above 65000"}).json()
    assert j["source"] == "gemini" and j["model"] == MODEL and j["fallback_reason"] is None


# ---------------------------------------------------------------- model verification endpoint
def test_model_check_not_configured(ctx):
    r = ctx.c.get("/api/health/gemini", headers=ctx.h).json()
    assert r["configured"] is False and r["ok"] is False and r["code"] == "not_configured"


def test_model_check_ok_and_failure(ctx, gem):
    gem(lambda s, c: resp({}), get=lambda model: SimpleNamespace(name=f"models/{model}"))
    ok = ctx.c.get("/api/health/gemini", headers=ctx.h).json()
    assert ok["ok"] is True and ok["model"] == MODEL

    def missing(model):
        raise errors.ClientError(404, {"error": {"message": f"models/{model} is not found key={FAKE_KEY}"}})
    gem(lambda s, c: resp({}), get=missing)
    bad = ctx.c.get("/api/health/gemini", headers=ctx.h)
    j = bad.json()
    assert j["ok"] is False and j["code"] == "model_not_found" and MODEL in j["message"] and FAKE_KEY not in bad.text


def test_model_check_requires_auth(client):
    assert client.get("/api/health/gemini").status_code == 401


# ---------------------------------------------------------------- REAL SDK path (no _client mock)
@pytest.fixture
def fake_gemini_server():
    """A local HTTP server speaking just enough of the Gemini REST API. Exercises the real google-genai code path,
    which is what the earlier mock-only tests could not: they missed the 'client has been closed' bug."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("content-length", 0)))
            seen.append((self.path, json.loads(body or b"{}")))
            out = {"candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps({"summary": "from the fake server"})}]}, "finishReason": "STOP"}]}
            data = json.dumps(out).encode()
            self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            data = json.dumps({"name": "models/gemini-3.8-flash"}).encode()
            self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = get_settings()
    old = (s.gemini_api_key, s.gemini_model, s.gemini_base_url)
    s.gemini_api_key, s.gemini_model, s.gemini_base_url = FAKE_KEY, MODEL, f"http://127.0.0.1:{srv.server_port}"
    gemini._clients.clear()
    yield seen
    s.gemini_api_key, s.gemini_model, s.gemini_base_url = old
    gemini._clients.clear()
    srv.shutdown()


def test_real_sdk_call_succeeds_and_survives_garbage_collection(fake_gemini_server):
    """Regression: a temporary SDK client used to be garbage-collected mid-call -> 'client has been closed'."""
    import gc
    from app.agents.shopping import Explanation
    for _ in range(3):
        gc.collect()
        out = gemini.generate_structured("sys", "hello", Explanation, purpose="test")
        assert out.summary == "from the fake server"
    path, body = fake_gemini_server[0]
    assert path.endswith(f"models/{MODEL}:generateContent") and body["generationConfig"]["responseMimeType"] == "application/json"
    assert "tools" not in body                                         # no function calling is ever registered


def test_real_sdk_model_check_and_search_end_to_end(ctx, fake_gemini_server):
    assert ctx.c.get("/api/health/gemini", headers=ctx.h).json()["ok"] is True
    r = ctx.c.post("/api/products/search", headers=ctx.h, json={"query": "Asus Vivobook 16 X1605"}).json()
    # the fake server returns {"summary": ...} for every call, so intent parsing fails validation -> labelled fallback,
    # but the transport itself worked (no RuntimeError) and the summary call succeeded:
    assert r["summary_source"] == "gemini" and r["summary"] == "from the fake server"
    assert r["intent_fallback_reason"] != "unknown_error"


def test_connection_failure_is_a_network_error_not_a_runtime_error(ctx):
    s = get_settings()
    old = (s.gemini_api_key, s.gemini_base_url)
    s.gemini_api_key, s.gemini_base_url = FAKE_KEY, "http://127.0.0.1:9"      # nothing listens here
    gemini._clients.clear()
    try:
        r = ctx.c.post("/api/policies/parse", headers=ctx.h, json={"text": "Never spend above 75000"})
        assert r.status_code == 200                                    # falls back to the labelled rule-based parser
        assert r.json()["draft"]["source"] == "heuristic_fallback" and r.json()["fallback_reason"] == "network_error"
    finally:
        s.gemini_api_key, s.gemini_base_url = old
        gemini._clients.clear()


# ---------------------------------------------------------------- resilience: retries, fallback model, circuit breaker (REAL SDK, scripted server)
@pytest.fixture
def scripted_gemini(monkeypatch):
    """Local server whose generateContent responses follow a script of HTTP statuses (then 200). Records every request."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    state = {"script": [], "requests": []}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
            state["requests"].append((self.path, body))
            status = state["script"].pop(0) if state["script"] else 200
            if status == 200:
                out = {"candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps({"summary": f"answered by {self.path.split('/')[-1].split(':')[0]}"})}]}, "finishReason": "STOP"}]}
            else:
                out = {"error": {"code": status, "message": {400: "Unsupported thinking level for this model", 401: "API key not valid", 404: "model not found", 429: "RESOURCE_EXHAUSTED"}.get(status, "The model is overloaded. Please try again later."), "status": "UNAVAILABLE"}}
            data = json.dumps(out).encode()
            self.send_response(status); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = get_settings()
    old = (s.gemini_api_key, s.gemini_model, s.gemini_base_url, s.gemini_fallback_model, s.gemini_retries, s.gemini_thinking_level)
    s.gemini_api_key, s.gemini_model, s.gemini_base_url = FAKE_KEY, MODEL, f"http://127.0.0.1:{srv.server_port}"
    s.gemini_fallback_model, s.gemini_retries, s.gemini_thinking_level = "gemini-3.5-flash-lite", 2, ""
    monkeypatch.setattr(gemini, "_sleep", lambda secs: None)          # no real waiting in tests
    gemini.reset_state()
    yield state
    s.gemini_api_key, s.gemini_model, s.gemini_base_url, s.gemini_fallback_model, s.gemini_retries, s.gemini_thinking_level = old
    gemini.reset_state()
    srv.shutdown()


def call():
    from app.agents.shopping import Explanation
    return gemini.generate_structured("sys", "hello", Explanation, purpose="test")


def models_called(state):
    return [p.split("/")[-1].split(":")[0] for p, _ in state["requests"]]


def test_transient_503_is_retried_then_succeeds_on_primary(scripted_gemini):
    scripted_gemini["script"] = [503, 504]                                   # two Google-side failures, then OK (the user's exact errors)
    out = call()
    assert out.summary == f"answered by {MODEL}" and gemini.used_model() == (MODEL, False)
    assert models_called(scripted_gemini) == [MODEL] * 3


def test_persistent_overload_falls_back_to_lighter_model_and_labels_it(scripted_gemini):
    scripted_gemini["script"] = [503, 503, 504]                              # primary exhausted (3 attempts)
    out = call()
    assert out.summary == "answered by gemini-3.5-flash-lite"
    assert gemini.used_model() == ("gemini-3.5-flash-lite", True)           # the label must name the model that REALLY answered
    assert models_called(scripted_gemini) == [MODEL] * 3 + ["gemini-3.5-flash-lite"]


def test_total_outage_is_bounded_and_opens_circuit_breaker(scripted_gemini):
    scripted_gemini["script"] = [503] * 20
    with pytest.raises(gemini.GeminiUnavailable) as ei:
        call()
    assert ei.value.code == "upstream_error" and "models tried" in str(ei.value)
    n = len(scripted_gemini["requests"])
    assert n == 3 + 2                                                         # bounded: 3 primary + 2 fallback attempts, not unlimited
    with pytest.raises(gemini.GeminiUnavailable) as ei2:                      # next call fails FAST without touching the network
        call()
    assert ei2.value.code == "recently_unavailable" and len(scripted_gemini["requests"]) == n


def test_search_stays_fast_and_labelled_during_an_outage(ctx, scripted_gemini):
    scripted_gemini["script"] = [503] * 40
    r = ctx.c.post("/api/products/search", headers=ctx.h, json={"query": "Asus Vivobook 16 X1605"}).json()
    assert r["status"] == "matches_found"                                     # curated catalog still answers
    assert r["summary_source"] == "template" and r["intent_source"] == "heuristic"
    assert r["intent_fallback_reason"] == "upstream_error" and r["summary_fallback_reason"] == "recently_unavailable"
    assert len(scripted_gemini["requests"]) == 5                              # the SECOND Gemini call (summary) did not hammer a dead service


def test_wrong_primary_model_name_uses_fallback_instead_of_dying(scripted_gemini):
    scripted_gemini["script"] = [404]
    assert call().summary == "answered by gemini-3.5-flash-lite"
    assert gemini.used_model()[1] is True


@pytest.mark.parametrize("status,code", [(401, "invalid_api_key"), (403, "permission_denied")])
def test_key_problems_are_not_retried_and_have_no_fallback(scripted_gemini, status, code):
    scripted_gemini["script"] = [status]
    with pytest.raises(gemini.GeminiUnavailable) as ei:
        call()
    assert ei.value.code == code and len(scripted_gemini["requests"]) == 1


def test_no_temperature_or_thinking_override_by_default(scripted_gemini):
    """Gemini 3 docs: keep temperature at its default; some models reject thinking_level='minimal'. We send neither unless configured."""
    call()
    cfg = scripted_gemini["requests"][0][1]["generationConfig"]
    assert "temperature" not in cfg and "thinkingConfig" not in cfg
    assert cfg["responseMimeType"] == "application/json" and "tools" not in scripted_gemini["requests"][0][1]


def test_configured_thinking_level_is_sent_and_dropped_if_the_model_rejects_it(scripted_gemini):
    get_settings().gemini_thinking_level = "low"
    call()
    tc = scripted_gemini["requests"][0][1]["generationConfig"]["thinkingConfig"]
    assert (tc.get("thinking_level") or tc.get("thinkingLevel")).lower() == "low"      # the SDK serialises the key in snake_case
    scripted_gemini["requests"].clear()
    scripted_gemini["script"] = [400]                                         # model rejects the level
    out = call()
    assert out.summary == f"answered by {MODEL}"                              # succeeded on the same model...
    assert "thinkingConfig" in scripted_gemini["requests"][0][1]["generationConfig"] and "thinkingConfig" not in scripted_gemini["requests"][1][1]["generationConfig"]


def test_ui_label_data_names_fallback_model(ctx, scripted_gemini):
    scripted_gemini["script"] = [503, 503, 503]                               # intent call: primary exhausted -> fallback answers
    r = ctx.c.post("/api/products/search", headers=ctx.h, json={"query": "Asus Vivobook 16 X1605"}).json()
    # fake server returns {"summary": ..} for every call so intent validation fails (labelled), but the summary call used a healthy model
    assert r["summary_source"] == "gemini" and r["summary_model"] in (MODEL, "gemini-3.5-flash-lite")
    assert "summary_used_fallback_model" in r and "intent_used_fallback_model" in r
