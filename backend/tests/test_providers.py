"""Product provider layer (DummyJSON-shaped payloads served by a MOCK transport; the real API is not called in tests)."""
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.database.session import SessionLocal
from app.models import Product
from app.providers import service as provider_service
from app.providers.base import ProviderError
from app.providers.dummyjson import DummyJsonProvider, map_item, safe_image_url

PERFUME = {"id": 101, "title": "Calvin Klein CK One", "description": "Classic unisex fragrance.", "category": "fragrances", "price": 49.99,
           "rating": 4.6, "stock": 40, "tags": ["fragrances", "perfumes"], "brand": "Calvin Klein", "weight": 2, "warrantyInformation": "1 month warranty",
           "shippingInformation": "Ships in 1 month", "availabilityStatus": "In Stock", "returnPolicy": "30 days return policy",
           "thumbnail": "https://cdn.dummyjson.com/product-images/fragrances/ck-one/thumbnail.webp", "images": ["https://cdn.dummyjson.com/a.webp"]}
LIPSTICK = {"id": 7, "title": "Red Lipstick", "description": "Bold colour.", "category": "beauty", "price": 12.99, "stock": 3, "brand": "Essence",
            "availabilityStatus": "Low Stock", "thumbnail": "https://cdn.dummyjson.com/l.webp", "images": []}
SOLD_OUT = {"id": 55, "title": "Sold Out Perfume", "description": "gone", "category": "fragrances", "price": 20, "brand": "Acme", "availabilityStatus": "Out of Stock",
            "thumbnail": "https://cdn.dummyjson.com/s.webp", "images": []}
ALL = [PERFUME, LIPSTICK, SOLD_OUT]


def mock_provider(handler=None):
    calls = []

    def default(req: httpx.Request):
        calls.append(str(req.url))
        q = req.url.params.get("q", "").lower()
        hits = [p for p in ALL if any(w in " ".join([p["title"], p["category"], p.get("brand", ""), p["description"], " ".join(p.get("tags", []))]).lower() for w in q.split())]
        return httpx.Response(200, json={"products": hits, "total": len(hits), "skip": 0, "limit": 20})
    prov = DummyJsonProvider(transport=httpx.MockTransport(handler or default))
    prov.calls = calls
    return prov


@pytest.fixture
def providers_on(monkeypatch):
    """Enable the dummyjson provider with a mock transport."""
    s = get_settings()
    old = s.product_providers
    s.product_providers = "curated,dummyjson"
    provider_service.clear_cache()
    holder = {"prov": mock_provider()}
    monkeypatch.setattr(provider_service, "build_providers", lambda: [holder["prov"]])
    yield holder
    s.product_providers = old
    provider_service.clear_cache()


def search(ctx, q):
    r = ctx.c.post("/api/products/search", headers=ctx.h, json={"query": q})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- mapping
def test_map_item_converts_price_and_fields():
    p = map_item(PERFUME, Decimal("83"))
    assert p.price_inr == Decimal("4149.17")                              # 49.99 USD x 83 (demo rate)
    assert (p.brand, p.model, p.category, p.product_type, p.availability) == ("Calvin Klein", "CK One", "beauty", "fragrance", "in_stock")
    assert p.image_url.startswith("https://cdn.dummyjson.com/") and p.merchant == "DummyJSON Demo Store" and p.source == "provider:dummyjson"
    assert map_item(LIPSTICK, Decimal("83")).availability == "limited_stock" and map_item(SOLD_OUT, Decimal("83")).availability == "out_of_stock"


@pytest.mark.parametrize("url,ok", [("https://cdn.dummyjson.com/x.webp", True), ("https://i.dummyjson.com/x.jpg", True), ("http://cdn.dummyjson.com/x.webp", False),
                                    ("javascript:alert(1)", False), ("https://evil.example.com/x.png", False), ("https://dummyjson.com.evil.com/x.png", False),
                                    ("data:image/svg+xml;base64,AAAA", False), (None, False), (123, False)])
def test_image_urls_are_restricted_to_https_provider_hosts(url, ok):
    assert (safe_image_url(url) is not None) is ok


@pytest.mark.parametrize("bad", [{}, {"id": 1}, {"id": 1, "title": "", "price": 5}, {"id": 1, "title": "x", "price": -1}, {"id": 1, "title": "x", "price": "abc"}])
def test_malformed_provider_items_are_skipped_not_raised(bad):
    assert map_item(bad, Decimal("83")) is None


def test_unknown_category_maps_to_other():
    p = map_item({"id": 9, "title": "Mystery", "price": 1, "category": "space-gadgets"}, Decimal("83"))
    assert p.category == "other" and p.product_type == "space_gadgets"


def test_malicious_provider_image_is_dropped():
    p = map_item({**PERFUME, "thumbnail": "javascript:alert(1)", "images": ["https://evil.example.com/a.png"]}, Decimal("83"))
    assert p.image_url is None


# ---------------------------------------------------------------- provider failures are safe and visible
@pytest.mark.parametrize("handler,code", [
    (lambda r: httpx.Response(500), "http_error"),
    (lambda r: httpx.Response(200, text="<html>not json</html>"), "bad_response"),
    (lambda r: httpx.Response(200, json={"nope": 1}), "bad_response"),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectTimeout("t")), "timeout"),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")), "network_error"),
])
def test_provider_errors_are_classified(handler, code):
    with pytest.raises(ProviderError) as ei:
        mock_provider(handler).search("perfume", 10)
    assert ei.value.code == code and "http" not in ei.value.message.lower().replace("http ", "")  # no URLs/secrets in messages


# ---------------------------------------------------------------- caching & end-to-end
def test_search_pulls_provider_products_with_real_images_and_labels(ctx, providers_on):
    r = search(ctx, "perfume")
    assert r["provider_status"][0]["ok"] is True and r["provider_status"][0]["count"] >= 2
    ck = [i for i in r["matches"] if i["product"]["brand"] == "Calvin Klein"][0]
    p = ck["product"]
    assert p["image_url"].startswith("https://cdn.dummyjson.com/") and p["image_source"] == "provider_photo" and p["source"] == "provider:dummyjson"
    assert p["category"] == "beauty" and p["product_type"] == "fragrance" and Decimal(p["price"]) == Decimal("4149.17")
    assert ck["merchant_approved"] is True                                   # the demo setup pre-approves "DummyJSON Demo Store"
    assert not any(i["product"]["name"] == "Sold Out Perfume" for i in r["matches"])      # out of stock is never a match


def test_provider_products_are_cached_in_db_and_upsert_is_idempotent(ctx, providers_on):
    search(ctx, "perfume")
    with SessionLocal() as db:
        rows = db.scalars(select(Product).where(Product.source == "provider:dummyjson")).all()
        assert {r.sku for r in rows} >= {"dummyjson-101", "dummyjson-55"}
        n = len(rows)
    provider_service.clear_cache()
    search(ctx, "perfume")
    with SessionLocal() as db:
        assert len(db.scalars(select(Product).where(Product.source == "provider:dummyjson")).all()) == n   # no duplicates


def test_provider_results_are_cached_between_searches(ctx, providers_on):
    search(ctx, "perfume")
    first = len(providers_on["prov"].calls)
    search(ctx, "perfume")
    assert len(providers_on["prov"].calls) == first                       # served from the TTL cache, no extra HTTP


def test_provider_failure_falls_back_to_curated_and_says_so(ctx, providers_on):
    providers_on["prov"] = mock_provider(lambda r: httpx.Response(503))
    r = search(ctx, "Asus Vivobook 16 X1605")
    assert [m["product"]["sku"] for m in r["matches"]] == ["LT-ASUS-VB16"]  # curated catalog still answers
    st = r["provider_status"][0]
    assert st["ok"] is False and st["code"] == "http_error" and "503" in st["message"]


def test_curated_only_mode_never_calls_providers(ctx, monkeypatch):
    def boom():
        raise AssertionError("providers must not be built when only 'curated' is enabled")
    monkeypatch.setattr(provider_service, "build_providers", boom)
    r = search(ctx, "laptop")
    assert r["provider_status"] == []


def test_provider_product_goes_through_policy_engine_and_paypal_conversion(ctx, providers_on, fake_pp):
    ag = ctx.c.post("/api/agents", headers=ctx.h, json={"agent_name": "BeautyAgent", "max_transaction": "20000", "allowed_categories": ["beauty"]}).json()
    pid = [i for i in search(ctx, "lipstick")["matches"] if i["product"]["brand"] == "Essence"][0]["product"]["id"]
    p = ctx.c.post("/api/proposals", headers=ctx.h, json={"agent_id": ag["agent_id"], "product_id": pid}).json()
    assert p["decision"] == "APPROVED" and p["amount"] == "1078.17" and p["merchant"] == "DummyJSON Demo Store"
    order = ctx.c.post("/api/payments/create-order", headers=ctx.h, json={"proposal_id": p["id"]}).json()
    assert order["charge_amount"] == "12.99" and order["charge_currency"] == "USD"      # 1078.17 INR / 83 == the provider's USD price


def test_provider_merchant_not_on_allowlist_needs_review_until_user_approves_it(client, providers_on):
    from tests.conftest import make_user
    h = make_user(client, "fresh@example.com")
    assert client.post("/api/policies", headers=h, json={"max_budget": "75000", "approval_threshold": "25000", "approved_merchants": ["Other Shop"]}).status_code == 201
    ag = client.post("/api/agents", headers=h, json={"agent_name": "BeautyAgent", "max_transaction": "20000", "allowed_categories": ["beauty"]}).json()
    r = client.post("/api/products/search", headers=h, json={"query": "lipstick"}).json()
    hit = [i for i in r["matches"] if i["product"]["brand"] == "Essence"][0]
    assert hit["merchant_approved"] is False                                   # the UI shows this and offers an explicit approve button
    p = client.post("/api/proposals", headers=h, json={"agent_id": ag["agent_id"], "product_id": hit["product"]["id"]}).json()
    assert p["decision"] == "REVIEW" and p["state"] == "PENDING_APPROVAL"       # never auto-approved
    assert client.post("/api/merchants", headers=h, json={"name": "DummyJSON Demo Store"}).status_code == 201
    r2 = client.post("/api/products/search", headers=h, json={"query": "lipstick"}).json()
    assert [i for i in r2["matches"] if i["product"]["brand"] == "Essence"][0]["merchant_approved"] is True


def test_approve_merchant_is_idempotent_and_audited(ctx):
    for _ in range(2):
        assert ctx.c.post("/api/merchants", headers=ctx.h, json={"name": "  Some   Shop "}).status_code == 201
    ms = ctx.c.get("/api/merchants", headers=ctx.h).json()["approved_merchants"]
    assert ms.count("Some Shop") == 1
    logs = ctx.c.get("/api/audit-logs?action=policy.merchant", headers=ctx.h).json()
    assert len(logs) == 1 and logs[0]["details"]["merchant"] == "Some Shop"


def test_demo_agents_top_up_creates_only_missing_agents(ctx):
    r = ctx.c.post("/api/demo/agents", headers=ctx.h).json()
    assert r["created"] == ["GeneralShoppingAgent"]                          # seed already had Fashion/Book agents
    gen = [a for a in ctx.c.get("/api/agents", headers=ctx.h).json() if a["agent_name"] == "GeneralShoppingAgent"][0]
    assert {"electronics", "beauty", "groceries", "home", "sports", "accessories", "automotive", "clothing"} <= set(gen["allowed_categories"])
    assert ctx.c.post("/api/demo/agents", headers=ctx.h).json()["created"] == []   # idempotent


def test_understood_type_with_no_products_says_so_instead_of_claiming_confusion(ctx, providers_on):
    providers_on["prov"] = mock_provider(lambda r: httpx.Response(503))
    r = search(ctx, "perfume under 20000")
    assert r["status"] == "nothing_found" and r["requirements"]["product_type"] == "fragrance"
    assert any("No fragrance products are in the catalog right now" in n for n in r["notes"])
    assert not any("couldn't tell" in n for n in r["notes"])
    assert r["provider_status"][0]["ok"] is False and r["provider_status"][0]["code"] == "http_error"


CHAIR = {"id": 301, "title": "Knoll Saarinen Executive Conference Chair", "description": "A classic office chair.", "category": "furniture", "price": 499.99,
         "brand": "Knoll", "availabilityStatus": "In Stock", "tags": ["furniture", "office chairs"], "thumbnail": "https://cdn.dummyjson.com/c.webp", "images": []}
SOFA = {"id": 302, "title": "Annibale Colombo Sofa", "description": "Italian sofa.", "category": "furniture", "price": 2499.99, "brand": "Annibale Colombo",
        "availabilityStatus": "In Stock", "tags": ["furniture"], "thumbnail": "https://cdn.dummyjson.com/s.webp", "images": []}


def test_provider_chair_with_generic_furniture_type_is_found_for_chair_searches(ctx, providers_on):
    """Regression: the provider returned 1 product for 'chair' (type 'furniture') but the UI only showed the built-in chair."""
    providers_on["prov"] = mock_provider(lambda r: httpx.Response(200, json={"products": [CHAIR, SOFA], "total": 2, "skip": 0, "limit": 20}))
    r = search(ctx, "office chair under 50000")
    names = [i["product"]["name"] for i in r["matches"] + r["alternatives"]]
    assert "Knoll Saarinen Executive Conference Chair" in names and "ErgoMesh Office Chair" in names
    assert "Annibale Colombo Sofa" not in names                       # a sofa is not a chair
    chair = [i for i in r["results"] if i["product"]["brand"] == "Knoll"][0]
    assert chair["product"]["image_url"].startswith("https://cdn.dummyjson.com/") and chair["kind"] == "match"
