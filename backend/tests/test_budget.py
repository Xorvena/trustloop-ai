"""Budget behaviour: unpaid authorizations must not reserve budget forever (reported bug: Aero 14 approved, never paid, then every
later purchase was BLOCKED with 'remaining budget 12010')."""
from decimal import Decimal

from tests.conftest import expire_approvals


def checks(p):
    return {c["rule"]: c for c in p["decision_explanation"]["checks"]}


def authorize_aero14_without_paying(ctx):
    p = ctx.propose("laptop", "LT-AERO14").json()          # 62,990 > 25,000 threshold -> needs approval
    assert p["decision"] == "REQUIRES_APPROVAL"
    assert ctx.approve(p["id"]).status_code == 200
    assert ctx.c.get(f"/api/proposals/{p['id']}", headers=ctx.h).json()["state"] == "AUTHORIZED"
    return p


def test_reproduces_the_reported_block_while_authorization_is_live(ctx):
    authorize_aero14_without_paying(ctx)
    p = ctx.propose("laptop", "LT-ASUS-VB16").json()        # 52,990 would exceed 75,000 - 62,990
    assert p["decision"] == "BLOCKED" and checks(p)["budget_remaining"]["passed"] is False
    d = checks(p)["budget_remaining"]["detail"]
    assert "12010" in d and "already committed 62990" in d   # the explanation now says WHY (what is already committed)


def test_expired_unpaid_authorization_stops_reserving_budget(ctx):
    a = authorize_aero14_without_paying(ctx)
    expire_approvals(a["id"])                                # 30 minutes pass without payment
    p = ctx.propose("laptop", "LT-ASUS-VB16").json()
    assert checks(p)["budget_remaining"]["passed"] is True and p["decision"] == "REQUIRES_APPROVAL"
    assert ctx.c.get(f"/api/proposals/{a['id']}", headers=ctx.h).json()["state"] == "EXPIRED"
    actions = [x["action"] for x in ctx.c.get(f"/api/audit-logs?proposal_id={a['id']}", headers=ctx.h).json()]
    assert "authorization.expired" in actions


def test_cancelling_an_unpaid_proposal_frees_the_budget(ctx):
    a = authorize_aero14_without_paying(ctx)
    r = ctx.c.post(f"/api/proposals/{a['id']}/cancel", headers=ctx.h)
    assert r.status_code == 200 and r.json()["state"] == "CANCELLED"
    p = ctx.propose("laptop", "LT-ASUS-VB16").json()
    assert checks(p)["budget_remaining"]["passed"] is True
    logs = [x["action"] for x in ctx.c.get(f"/api/audit-logs?proposal_id={a['id']}", headers=ctx.h).json()]
    assert "proposal.cancelled" in logs and "approval.invalidated" in logs


def test_cancelled_proposal_cannot_be_paid(ctx, fake_pp):
    a = authorize_aero14_without_paying(ctx)
    ctx.c.post(f"/api/proposals/{a['id']}/cancel", headers=ctx.h)
    r = ctx.c.post("/api/payments/create-order", headers=ctx.h, json={"proposal_id": a["id"]})
    assert r.status_code == 409 and fake_pp.orders == {}


def test_cancel_after_order_created_blocks_capture(ctx, fake_pp):
    a = authorize_aero14_without_paying(ctx)
    order = ctx.c.post("/api/payments/create-order", headers=ctx.h, json={"proposal_id": a["id"]}).json()
    assert ctx.c.post(f"/api/proposals/{a['id']}/cancel", headers=ctx.h).status_code == 200
    r = ctx.c.post("/api/payments/capture", headers=ctx.h, json={"paypal_order_id": order["paypal_order_id"]})
    assert r.status_code == 409 and fake_pp.capture_calls == 0          # the buyer approving in PayPal can no longer lead to a capture


def test_captured_purchases_keep_counting_and_cannot_be_cancelled(ctx, fake_pp):
    p = ctx.propose("laptop", "LT-LITE13").json()
    ctx.approve(p["id"])
    oid = ctx.c.post("/api/payments/create-order", headers=ctx.h, json={"proposal_id": p["id"]}).json()["paypal_order_id"]
    assert ctx.c.post("/api/payments/capture", headers=ctx.h, json={"paypal_order_id": oid}).status_code == 200
    assert ctx.c.post(f"/api/proposals/{p['id']}/cancel", headers=ctx.h).status_code == 409
    b = ctx.c.get("/api/budget", headers=ctx.h).json()
    assert Decimal(b["committed"]) == Decimal("31990") and Decimal(b["remaining"]) == Decimal("43010")
    assert [i["state"] for i in b["items"]] == ["CAPTURED"] and b["items"][0]["cancellable"] is False


def test_budget_endpoint_lists_what_is_using_the_budget(ctx):
    a = authorize_aero14_without_paying(ctx)
    b = ctx.c.get("/api/budget", headers=ctx.h).json()
    assert b["policy_active"] is True and b["currency"] == "INR"
    assert (Decimal(b["max_budget"]), Decimal(b["committed"]), Decimal(b["remaining"])) == (Decimal("75000"), Decimal("62990"), Decimal("12010"))
    item = b["items"][0]
    assert item["proposal_id"] == a["id"] and item["product_name"].startswith("Aero 14") and item["state"] == "AUTHORIZED" and item["cancellable"] is True
    assert item["authorization_expires_at"]


def test_budget_endpoint_without_policy(ctx):
    pid = ctx.c.get("/api/policies", headers=ctx.h).json()[0]["id"]
    ctx.c.patch(f"/api/policies/{pid}", headers=ctx.h, json={"is_active": False})
    assert ctx.c.get("/api/budget", headers=ctx.h).json()["policy_active"] is False


def test_cancel_is_owner_only_and_not_for_blocked(ctx, client):
    from tests.conftest import make_user
    a = authorize_aero14_without_paying(ctx)
    other = make_user(client, "mallory@example.com")
    assert client.post(f"/api/proposals/{a['id']}/cancel", headers=other).status_code == 404
    blocked = ctx.propose("laptop", "LT-TITAN16").json()
    assert ctx.c.post(f"/api/proposals/{blocked['id']}/cancel", headers=ctx.h).status_code == 409


def test_cancelling_pending_proposal_invalidates_its_approval_request(ctx):
    p = ctx.propose("laptop", "LT-LITE13").json()
    assert ctx.c.post(f"/api/proposals/{p['id']}/cancel", headers=ctx.h).status_code == 200
    assert ctx.c.get("/api/approvals/pending", headers=ctx.h).json() == []
