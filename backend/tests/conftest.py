import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="trustloop-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["JWT_SECRET"] = "test-secret-test-secret-1234"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["GEMINI_API_KEY"] = ""
os.environ["PRODUCT_PROVIDERS"] = "curated"   # tests never call external providers unless they inject a mock
os.environ["PAYPAL_CLIENT_ID"] = ""
os.environ["PAYPAL_CLIENT_SECRET"] = ""
os.environ["PAYPAL_WEBHOOK_ID"] = ""

import itertools  # noqa: E402
from datetime import timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agents.catalog import seed_catalog  # noqa: E402
from app.database.session import Base, SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.payments import paypal  # noqa: E402


class FakePayPal:
    """TEST DOUBLE ONLY. Never used by the running app."""
    def __init__(self):
        self.orders: dict[str, dict] = {}
        self.capture_calls = 0
        self.webhook_ok = True
        self.tamper_amount = False
        self.decline = False
        self._n = itertools.count(1)

    def create_order(self, *, reference_id, amount, currency, description, request_id):
        for o in self.orders.values():  # PayPal-Request-Id idempotency
            if o["request_id"] == request_id:
                return {"id": o["id"], "status": "CREATED"}
        oid = f"ORDER{next(self._n):04d}"
        self.orders[oid] = {"id": oid, "reference_id": reference_id, "amount": amount, "currency": currency, "request_id": request_id}
        return {"id": oid, "status": "CREATED"}

    def capture_order(self, order_id, request_id):
        self.capture_calls += 1
        if self.decline:
            raise paypal.PayPalError(422, {"details": [{"issue": "INSTRUMENT_DECLINED"}]})
        o = self.orders[order_id]
        value = o["amount"] + (Decimal("1.00") if self.tamper_amount else 0)
        return {"id": order_id, "status": "COMPLETED", "purchase_units": [{"reference_id": o["reference_id"], "payments": {"captures": [
            {"id": f"CAP{order_id}", "status": "COMPLETED", "amount": {"value": f"{value:.2f}", "currency_code": o["currency"]}}]}}]}

    def verify_webhook(self, headers, event):
        return self.webhook_ok


@pytest.fixture(autouse=True)
def fresh_db():
    from app.agents import gemini
    gemini.reset_state()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_catalog(db)
    yield


@pytest.fixture
def fake_pp(monkeypatch):
    fp = FakePayPal()
    monkeypatch.setattr(paypal, "get_client", lambda: fp)
    return fp


@pytest.fixture
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


class Ctx:
    def __init__(self, client, headers, agents, products):
        self.c, self.h, self.agents, self.products = client, headers, agents, products

    def propose(self, agent_key: str, sku: str, **kw):
        r = self.c.post("/api/proposals", headers=self.h, json={"agent_id": self.agents[agent_key], "product_id": self.products[sku], **kw})
        return r

    def approve(self, proposal_id: str, decision="approve"):
        ap = [a for a in self.c.get("/api/approvals/pending", headers=self.h).json() if a["proposal_id"] == proposal_id]
        assert ap, "no pending approval"
        return self.c.post(f"/api/approvals/{ap[0]['id']}/decision", headers=self.h, json={"decision": decision})


def make_user(client, email="a@example.com"):
    r = client.post("/api/auth/register", json={"email": email, "name": "Tester", "password": "password123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def ctx(client):
    h = make_user(client)
    seeded = client.post("/api/demo/seed", headers=h).json()
    codes = seeded["agents"]
    prods = {p["sku"]: p["id"] for p in client.get("/api/products", headers=h).json()}
    return Ctx(client, h, {"laptop": codes[0], "furniture": codes[1], "inactive": codes[2]}, prods)


def expire_approvals(proposal_id: str):
    from app.models import Approval, utcnow
    from sqlalchemy import select
    with SessionLocal() as db:
        for a in db.scalars(select(Approval).where(Approval.proposal_id == proposal_id)):
            a.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
