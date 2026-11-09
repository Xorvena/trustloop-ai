"""PayPal REST client (OAuth 2.0 + Orders v2 + webhook signature verification). Backend-only: the secret never leaves here.

Endpoints used (PayPal REST, sandbox base https://api-m.sandbox.paypal.com):
  POST /v1/oauth2/token                          client_credentials
  POST /v2/checkout/orders                       create order (intent CAPTURE), PayPal-Request-Id for idempotency
  POST /v2/checkout/orders/{id}/capture          capture approved order, PayPal-Request-Id for idempotency
  POST /v1/notifications/verify-webhook-signature  verify webhook authenticity
"""
import time
from decimal import Decimal

import httpx

from app.core.config import get_settings
from app.core.errors import ServiceError


class PayPalError(Exception):
    def __init__(self, status: int, body: dict | str):
        super().__init__(f"PayPal HTTP {status}")
        self.status, self.body = status, body

    @property
    def issues(self) -> list[str]:
        if isinstance(self.body, dict):
            return [d.get("issue", "") for d in self.body.get("details", [])]
        return []


class PayPalClient:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        s = get_settings()
        if not (s.paypal_client_id and s.paypal_client_secret):
            raise ServiceError(503, "paypal_not_configured", "PayPal sandbox credentials are not configured on the server.")
        self._s = s
        self._http = httpx.Client(base_url=s.paypal_base_url, timeout=20.0, transport=transport)
        self._token: str | None = None
        self._exp = 0.0

    def _auth(self) -> str:
        if self._token and time.time() < self._exp - 30:
            return self._token
        r = self._http.post("/v1/oauth2/token", data={"grant_type": "client_credentials"},
                            auth=(self._s.paypal_client_id, self._s.paypal_client_secret))
        if r.status_code != 200:
            raise PayPalError(r.status_code, "oauth failed")
        j = r.json()
        self._token, self._exp = j["access_token"], time.time() + int(j.get("expires_in", 300))
        return self._token

    def _req(self, method: str, path: str, *, json: dict | None = None, request_id: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._auth()}", "Content-Type": "application/json"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        try:
            r = self._http.request(method, path, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise PayPalError(0, f"network error: {type(exc).__name__}") from exc
        body = r.json() if r.content else {}
        if r.status_code >= 400:
            raise PayPalError(r.status_code, body)
        return body

    def create_order(self, *, reference_id: str, amount: Decimal, currency: str, description: str, request_id: str) -> dict:
        # NOTE: no `payment_source`. An order created with payment_source.paypal is restricted to the PayPal wallet, which breaks the
        # "Debit or Credit Card" button of the JS SDK. `application_context` is funding-agnostic.
        payload = {"intent": "CAPTURE", "purchase_units": [{
            "reference_id": reference_id, "custom_id": reference_id, "description": description[:127],
            "amount": {"currency_code": currency, "value": f"{amount:.2f}"}}],
            "application_context": {"shipping_preference": "NO_SHIPPING", "user_action": "PAY_NOW"}}
        return self._req("POST", "/v2/checkout/orders", json=payload, request_id=request_id)

    def capture_order(self, order_id: str, request_id: str) -> dict:
        return self._req("POST", f"/v2/checkout/orders/{order_id}/capture", json={}, request_id=request_id)

    def verify_webhook(self, headers: dict, event: dict) -> bool:
        h = {k.lower(): v for k, v in headers.items()}
        if not self._s.paypal_webhook_id:
            raise ServiceError(503, "webhook_not_configured", "PAYPAL_WEBHOOK_ID is not configured; refusing unverified webhooks.")
        try:
            body = {"auth_algo": h["paypal-auth-algo"], "cert_url": h["paypal-cert-url"], "transmission_id": h["paypal-transmission-id"],
                    "transmission_sig": h["paypal-transmission-sig"], "transmission_time": h["paypal-transmission-time"],
                    "webhook_id": self._s.paypal_webhook_id, "webhook_event": event}
        except KeyError:
            return False
        try:
            return self._req("POST", "/v1/notifications/verify-webhook-signature", json=body).get("verification_status") == "SUCCESS"
        except PayPalError:
            return False


def get_client() -> PayPalClient:  # overridable in tests via dependency/monkeypatch
    return PayPalClient()
