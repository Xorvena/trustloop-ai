"""The REAL PayPalClient against a mock HTTP transport: verifies what we actually send to PayPal (the other tests use a fake client)."""
import base64
import json
from decimal import Decimal

import httpx
import pytest

from app.core.config import get_settings
from app.payments.paypal import PayPalClient, PayPalError

CID, SECRET = "test-client-id", "test-client-secret"


@pytest.fixture
def pp():
    s = get_settings()
    old = (s.paypal_client_id, s.paypal_client_secret, s.paypal_webhook_id)
    s.paypal_client_id, s.paypal_client_secret, s.paypal_webhook_id = CID, SECRET, "WH-123"
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "TOKEN-1", "expires_in": 32000})
        if req.url.path == "/v2/checkout/orders":
            return httpx.Response(201, json={"id": "ORDER-1", "status": "CREATED"})
        if req.url.path.endswith("/capture"):
            return httpx.Response(201, json={"id": "ORDER-1", "status": "COMPLETED"})
        if req.url.path == "/v1/notifications/verify-webhook-signature":
            return httpx.Response(200, json={"verification_status": "SUCCESS"})
        return httpx.Response(404, json={})
    client = PayPalClient(transport=httpx.MockTransport(handler))
    yield client, seen
    s.paypal_client_id, s.paypal_client_secret, s.paypal_webhook_id = old


def test_oauth_uses_client_credentials_with_basic_auth_and_token_is_cached(pp):
    client, seen = pp
    client.create_order(reference_id="p1", amount=Decimal("10"), currency="USD", description="x", request_id="r1")
    client.create_order(reference_id="p2", amount=Decimal("10"), currency="USD", description="x", request_id="r2")
    tokens = [r for r in seen if r.url.path == "/v1/oauth2/token"]
    assert len(tokens) == 1                                                       # cached, not re-fetched per call
    assert tokens[0].headers["authorization"] == "Basic " + base64.b64encode(f"{CID}:{SECRET}".encode()).decode()
    assert b"grant_type=client_credentials" in tokens[0].content
    assert all(r.headers["authorization"] == "Bearer TOKEN-1" for r in seen if r.url.path != "/v1/oauth2/token")


def test_create_order_payload_is_funding_agnostic_and_idempotent(pp):
    client, seen = pp
    client.create_order(reference_id="prop-1", amount=Decimal("638.4337"), currency="USD", description="ASUS Vivobook 16", request_id="trustloop-order-prop-1")
    req = [r for r in seen if r.url.path == "/v2/checkout/orders"][0]
    body = json.loads(req.content)
    assert req.headers["paypal-request-id"] == "trustloop-order-prop-1"          # idempotency key
    assert body["intent"] == "CAPTURE"
    assert "payment_source" not in body                                          # would lock the order to the PayPal wallet and break the card button
    assert body["application_context"] == {"shipping_preference": "NO_SHIPPING", "user_action": "PAY_NOW"}
    unit = body["purchase_units"][0]
    assert unit["amount"] == {"currency_code": "USD", "value": "638.43"}          # string with exactly 2 decimals
    assert unit["reference_id"] == unit["custom_id"] == "prop-1"


def test_capture_uses_idempotency_key(pp):
    client, seen = pp
    client.capture_order("ORDER-1", request_id="trustloop-capture-ORDER-1")
    req = [r for r in seen if r.url.path.endswith("/capture")][0]
    assert req.url.path == "/v2/checkout/orders/ORDER-1/capture" and req.headers["paypal-request-id"] == "trustloop-capture-ORDER-1"


def test_webhook_verification_request_shape(pp):
    client, seen = pp
    headers = {"PayPal-Auth-Algo": "SHA256withRSA", "PayPal-Cert-Url": "https://api.sandbox.paypal.com/cert", "PayPal-Transmission-Id": "t1",
               "PayPal-Transmission-Sig": "sig", "PayPal-Transmission-Time": "2026-11-07T00:00:00Z"}
    assert client.verify_webhook(headers, {"id": "WH-EVENT"}) is True
    body = json.loads([r for r in seen if r.url.path.endswith("verify-webhook-signature")][0].content)
    assert body["webhook_id"] == "WH-123" and body["webhook_event"] == {"id": "WH-EVENT"} and body["transmission_sig"] == "sig"
    assert client.verify_webhook({"PayPal-Auth-Algo": "x"}, {}) is False          # missing headers => rejected


def test_paypal_errors_expose_issue_codes_not_secrets():
    s = get_settings()
    old = (s.paypal_client_id, s.paypal_client_secret)
    s.paypal_client_id, s.paypal_client_secret = CID, SECRET
    try:
        def handler(req):
            if req.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "T", "expires_in": 100})
            return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "CURRENCY_NOT_SUPPORTED"}]})
        with pytest.raises(PayPalError) as ei:
            PayPalClient(transport=httpx.MockTransport(handler)).create_order(reference_id="p", amount=Decimal("1"), currency="INR", description="d", request_id="r")
        assert ei.value.status == 422 and ei.value.issues == ["CURRENCY_NOT_SUPPORTED"] and SECRET not in str(ei.value)
    finally:
        s.paypal_client_id, s.paypal_client_secret = old


def test_create_order_error_message_shows_paypal_issue_code(ctx, monkeypatch):
    from app.payments import paypal

    class Rejecting:
        def create_order(self, **kw):
            raise paypal.PayPalError(422, {"details": [{"issue": "CURRENCY_NOT_SUPPORTED"}]})
    monkeypatch.setattr(paypal, "get_client", lambda: Rejecting())
    p = ctx.propose("laptop", "HP-WAVE").json()
    r = ctx.c.post("/api/payments/create-order", headers=ctx.h, json={"proposal_id": p["id"]})
    assert r.status_code == 502 and "CURRENCY_NOT_SUPPORTED" in r.json()["detail"]


def test_public_config_exposes_funding_option_and_no_secret(ctx):
    s = get_settings()
    old = (s.paypal_client_id, s.paypal_client_secret, s.paypal_disable_funding)
    s.paypal_client_id, s.paypal_client_secret, s.paypal_disable_funding = CID, SECRET, "card, paylater"
    try:
        r = ctx.c.get("/api/payments/config", headers=ctx.h)
        assert r.json()["disable_funding"] == "card,paylater" and r.json()["client_id"] == CID and SECRET not in r.text
    finally:
        s.paypal_client_id, s.paypal_client_secret, s.paypal_disable_funding = old
