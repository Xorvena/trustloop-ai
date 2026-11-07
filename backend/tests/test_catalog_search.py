"""Catalog + search behaviour: brand/model matching, unavailable products, alternatives, category-specific attributes,
images, category permissions. Gemini is NOT configured in these tests (rule-based parser + template summaries)."""
from decimal import Decimal

from sqlalchemy import select

from app.agents.catalog import CATALOG, CATEGORIES, TYPE_ATTRIBUTES, TYPE_TO_CATEGORY, seed_catalog
from app.agents.shopping import heuristic_requirements, model_relation
from app.database.session import SessionLocal
from app.models import Product


def search(ctx, q):
    r = ctx.c.post("/api/products/search", headers=ctx.h, json={"query": q})
    assert r.status_code == 200, r.text
    return r.json()


def skus(items):
    return [i["product"]["sku"] for i in items]


# ---------------------------------------------------------------- brand / model matching
def test_exact_brand_and_model_match(ctx):
    r = search(ctx, "Asus Vivobook 16 X1605")
    assert r["status"] == "matches_found"
    assert skus(r["matches"]) == ["LT-ASUS-VB16"]
    model_check = [c for c in r["matches"][0]["checks"] if c["key"] == "model"][0]
    assert model_check["met"] and model_check["detail"] == "exact model match"


def test_user_example_vivobook_x16_is_not_silently_replaced(ctx):
    q = ("Find a laptop for software development. My maximum budget is ₹75,000. I need brand-Asus VivobookX16, "
         "16GB RAM, 512GB SSD and good battery life.")
    r = search(ctx, q)
    assert r["requirements"]["brand"] == "ASUS" and r["requirements"]["model"] == "VivobookX16"   # requirement kept
    assert r["status"] == "no_exact_match" and r["matches"] == []                                  # nothing claimed as a match
    assert any("isn't in the catalog" in n for n in r["notes"])
    assert any("Closest models from the same line" in n for n in r["notes"])
    # same-brand alternatives come first and say exactly which requirement they miss
    assert skus(r["alternatives"])[:2] == ["LT-ASUS-VB16", "LT-ASUS-VB15"] or set(skus(r["alternatives"])[:2]) == {"LT-ASUS-VB16", "LT-ASUS-VB15"}
    for alt in r["alternatives"][:2]:
        assert any("Model:" in u for u in alt["unmet"]) and alt["meets_requirements"] is False
    assert "meets all" not in r["summary"].lower() and r["summary"].startswith("No exact match")
    assert r["summary_source"] == "template"


def test_model_relation_rules():
    assert model_relation("Vivobook 16 X1605", "Vivobook 16 X1605") == "exact"
    assert model_relation("Vivobook 16", "Vivobook 16 X1605") == "contains"
    assert model_relation("Galaxy A55", "Galaxy A55 5G") == "contains"
    assert model_relation("Pixel 8", "Pixel 8a") != "contains"          # 8 != 8a
    assert model_relation("VivobookX16", "Vivobook 16 X1605") == "same_line"
    assert model_relation("Vivobook X16", "Vivobook 16 X1605") == "same_line"
    assert model_relation("ThinkPad", "Vivobook 16 X1605") is None


def test_brand_not_in_catalog_is_stated_clearly(ctx):
    r = search(ctx, "Acer Aspire laptop under 50000")
    assert r["status"] != "matches_found"
    assert any("No products from the brand 'Acer' are in the catalog" in n for n in r["notes"])
    assert all(i["product"]["brand"] != "Acer" for i in r["results"])


def test_brand_requested_is_never_ignored_in_results(ctx):
    r = search(ctx, "HP laptop under 70000")
    assert skus(r["matches"]) == ["LT-HP-PAV15"]
    assert all(any(c["key"] == "brand" for c in i["checks"]) for i in r["results"])


# ---------------------------------------------------------------- availability
def test_out_of_stock_is_not_a_match_and_cannot_be_proposed(ctx):
    r = search(ctx, "Dell Inspiron 14 laptop")
    assert "LT-DELL-INS14" not in skus(r["matches"])
    alt = [a for a in r["alternatives"] if a["product"]["sku"] == "LT-DELL-INS14"][0]
    assert any("out of stock" in u for u in alt["unmet"])
    assert any("currently out of stock" in n for n in r["notes"])
    prod_id = alt["product"]["id"]
    p = ctx.c.post("/api/proposals", headers=ctx.h, json={"agent_id": ctx.agents["laptop"], "product_id": prod_id})
    assert p.status_code == 409 and p.json()["error"] == "product_unavailable"
    assert ctx.c.get("/api/proposals", headers=ctx.h).json() == []   # nothing was created


# ---------------------------------------------------------------- alternatives
def test_alternatives_are_separate_and_explain_unmet_requirements(ctx):
    r = search(ctx, "laptop with 32GB RAM under 60000")
    assert r["status"] == "no_exact_match" and r["matches"] == []
    assert r["alternatives"] and all(a["kind"] == "alternative" for a in r["alternatives"])
    assert any("RAM" in u for a in r["alternatives"] for u in a["unmet"])
    assert any("over budget" in u for a in r["alternatives"] for u in a["unmet"])
    assert r["results"][0]["kind"] == "alternative"


def test_matches_listed_before_alternatives_and_never_overclaim(ctx):
    r = search(ctx, "laptop 16GB RAM 512GB SSD under 50000")
    assert r["status"] == "matches_found" and r["matches"]
    assert all(m["meets_requirements"] and not m["unmet"] for m in r["matches"])
    assert all(not a["meets_requirements"] and a["unmet"] for a in r["alternatives"])
    kinds = [i["kind"] for i in r["results"]]
    assert kinds == sorted(kinds, key=lambda k: 0 if k == "match" else 1)


def test_unverifiable_terms_are_reported_not_dropped(ctx):
    r = search(ctx, "gaming laptop with touchscreen 16GB RAM under 70k")
    assert {"gaming", "touchscreen"} <= set(r["unverifiable_terms"])
    assert "could not verify" in r["summary"].lower() and "gaming" in r["summary"]


# ---------------------------------------------------------------- category-specific attributes
def test_footwear_filters_use_size_color_gender_not_laptop_specs(ctx):
    r = search(ctx, "running shoes for men size 9 black under ₹4000")
    assert set(skus(r["matches"])) == {"FW-NIKE-REV7", "FW-ADI-DURAMO"}
    keys = {c["key"] for m in r["matches"] for c in m["checks"]}
    assert {"size", "color", "gender", "shoe_type", "budget"} <= keys and not keys & {"ram", "storage", "battery_hours"}
    assert "FW-SKX-WALK" not in skus(r["matches"]) and "FW-PUMA-SMASH" not in skus(r["matches"])


def test_books_search_by_author_and_title(ctx):
    r = search(ctx, "Atomic Habits by James Clear")
    assert skus(r["matches"]) == ["BK-ATOMIC"]
    keys = {c["key"] for c in r["matches"][0]["checks"]}
    assert "author" in keys and "ram" not in keys


def test_clothing_size_not_available_is_explained(ctx):
    r = search(ctx, "Levis jeans size 40")
    assert r["matches"] == [] and r["status"] == "no_exact_match"
    assert any("Size: 40" in n for n in r["notes"])
    assert any("Size: 40" in u for u in r["alternatives"][0]["unmet"])


def test_smartphone_uses_battery_mah(ctx):
    r = search(ctx, "phone 8GB RAM 5000mah battery under 30000")
    assert set(skus(r["matches"])) == {"PH-1P-NORD", "PH-IQOO-Z9"}
    assert any(c["key"] == "battery_mah" for c in r["matches"][0]["checks"])


def test_rule_parser_extracts_structured_requirements():
    r = heuristic_requirements("Nike running shoes size 9", ["Nike"])
    assert (r.brand, r.product_type, r.size, r.shoe_type, r.model) == ("Nike", "shoes", "9", "running", None)
    r = heuristic_requirements("iPhone 15 128GB storage", [])
    assert (r.brand, r.product_type, r.model, r.min_storage_gb) == ("Apple", "smartphone", "iPhone 15", 128)
    assert heuristic_requirements("laptop under 1.5 lakh", []).max_budget == 150000


def test_search_with_no_identifiable_product_asks_for_more(ctx):
    r = search(ctx, "something nice please")
    assert r["status"] == "nothing_found" and r["matches"] == []
    assert any("couldn't tell what product" in n for n in r["notes"])


# ---------------------------------------------------------------- catalog integrity & images
def test_catalog_data_is_consistent():
    assert len(CATALOG) >= 30 and len({c[0] for c in CATALOG}) == len(CATALOG)
    assert {"laptop", "smartphone", "tshirt", "shoes", "book"} <= {c[4] for c in CATALOG}
    for sku, name, brand, model, ptype, merchant, price, avail, desc, specs, source in CATALOG:
        assert brand and model and merchant and Decimal(price) > 0, sku
        assert avail in ("in_stock", "limited_stock", "out_of_stock"), sku
        assert set(specs) <= set(TYPE_ATTRIBUTES[ptype]), (sku, set(specs) - set(TYPE_ATTRIBUTES[ptype]))
        assert ptype in TYPE_TO_CATEGORY
    assert set(TYPE_TO_CATEGORY.values()) == set(CATEGORIES)


def test_original_demo_prices_unchanged_for_scenarios(ctx):
    expected = {"HP-WAVE": "15000.00", "LT-LITE13": "31990.00", "LT-TITAN16": "82990.00", "LT-BUDGET": "27990.00", "LT-EVIL": "44990.00"}
    got = {p["sku"]: p["price"] for p in ctx.c.get("/api/products", headers=ctx.h).json()}
    assert all(Decimal(got[k]) == Decimal(v) for k, v in expected.items())


def test_seed_is_idempotent_and_upserts():
    with SessionLocal() as db:
        assert seed_catalog(db) == 0                      # fixture already seeded everything
        p = db.scalars(select(Product).where(Product.sku == "LT-ASUS-VB16")).one()
        p.availability = "out_of_stock"; db.commit()
        seed_catalog(db)
        assert db.scalars(select(Product).where(Product.sku == "LT-ASUS-VB16")).one().availability == "in_stock"  # curated data restored


def test_every_product_has_image_url_and_source_in_api(ctx):
    prods = ctx.c.get("/api/products", headers=ctx.h).json()
    assert len(prods) == len(CATALOG)
    for p in prods:
        assert p["image_url"].startswith("/catalog/") and p["image_url"].endswith(".svg")
        assert p["image_source"] == "illustration"          # honest label: generic illustration, not a product photo
        assert p["brand"] and p["model"] and p["availability"]
    r = search(ctx, "Asus Vivobook 16 X1605")
    assert r["matches"][0]["product"]["image_url"] == "/catalog/laptop.svg"


def test_missing_image_is_returned_as_null_not_invented(ctx):
    with SessionLocal() as db:
        p = db.scalars(select(Product).where(Product.sku == "BK-CLEANCODE")).one()
        p.image_url, p.image_source = None, None
        db.commit()
    prods = {p["sku"]: p for p in ctx.c.get("/api/products", headers=ctx.h).json()}
    assert prods["BK-CLEANCODE"]["image_url"] is None and prods["BK-CLEANCODE"]["image_source"] is None
    r = search(ctx, "Clean Code by Robert C. Martin")
    assert r["matches"][0]["product"]["image_url"] is None


def test_product_filters_and_categories_endpoint(ctx):
    books = ctx.c.get("/api/products?category=books", headers=ctx.h).json()
    assert books and all(p["product_type"] == "book" for p in books)
    assert all(p["brand"] == "Nike" for p in ctx.c.get("/api/products?brand=nike", headers=ctx.h).json())
    cats = ctx.c.get("/api/products/categories", headers=ctx.h).json()
    assert {"electronics", "clothing", "footwear", "books", "furniture"} <= set(cats["categories"])       # curated
    assert {"beauty", "groceries", "home", "sports", "accessories"} <= set(cats["categories"])          # added by the provider layer
    assert "shoes" in cats["type_attributes"]


# ---------------------------------------------------------------- agent category permissions still enforced
def test_agent_category_permissions_respected(ctx):
    prods = {p["sku"]: p["id"] for p in ctx.c.get("/api/products", headers=ctx.h).json()}
    agents = {a["agent_name"]: a["agent_id"] for a in ctx.c.get("/api/agents", headers=ctx.h).json()}

    def propose(agent, sku):
        return ctx.c.post("/api/proposals", headers=ctx.h, json={"agent_id": agents[agent], "product_id": prods[sku]}).json()
    shoes_by_fashion = propose("FashionAgent", "FW-NIKE-REV7")
    assert shoes_by_fashion["decision"] == "APPROVED"
    laptop_by_fashion = propose("FashionAgent", "LT-ASUS-VB16")
    assert laptop_by_fashion["decision"] == "BLOCKED"
    assert {c["rule"]: c["passed"] for c in laptop_by_fashion["decision_explanation"]["checks"]}["category_permission"] is False
    shoes_by_laptop_agent = propose("LaptopShoppingAgent", "FW-ADI-DURAMO")
    assert shoes_by_laptop_agent["decision"] == "BLOCKED"
    assert propose("BookAgent", "BK-CLEANCODE")["decision"] == "APPROVED"
    assert propose("BookAgent", "KB-MECH")["decision"] == "BLOCKED"


def test_approval_center_payload_includes_product_image(ctx):
    prods = {p["sku"]: p["id"] for p in ctx.c.get("/api/products", headers=ctx.h).json()}
    ctx.c.post("/api/proposals", headers=ctx.h, json={"agent_id": ctx.agents["laptop"], "product_id": prods["LT-LITE13"]})
    ap = ctx.c.get("/api/approvals/pending", headers=ctx.h).json()[0]
    assert ap["image_url"] == "/catalog/laptop.svg" and ap["image_source"] == "illustration"


def test_unrelated_out_of_stock_products_are_not_offered_as_alternatives(ctx):
    r = search(ctx, "Asus VivobookX16 laptop")
    assert "LT-DELL-INS14" not in skus(r["alternatives"])          # out of stock AND unrelated to the request
    r2 = search(ctx, "Dell laptop")                                 # ...but shown (with the reason) when the user asked for Dell
    assert "LT-DELL-INS14" in skus(r2["alternatives"])


def test_descriptive_words_do_not_become_hard_filters(ctx):
    """Regression for the user's chair search: 'back', 'lumbar', 'armrests'... were hard-required and everything failed."""
    q = "Find a high-back ergonomic office chair with adjustable lumbar support, 3D armrests, and breathable mesh fabric. Maximum budget is ₹20,000."
    r = search(ctx, q)
    assert r["status"] == "matches_found" and skus(r["matches"]) == ["CH-ERGO"]           # type + budget + material verified
    m = r["matches"][0]
    assert "back" not in " ".join(c["label"] for c in m["checks"])                       # no bogus "Mentions 'back'" check
    assert {"armrests", "adjustable"} <= set(r["unverifiable_terms"])                      # honest: not in any product data
    assert "Not confirmed" in r["summary"] or "could not verify" in r["summary"].lower()  # and the summary says so
    assert r["status"] == "matches_found" and "meets all" not in r["summary"].lower()


def test_whole_word_matching():
    from app.agents.shopping import has_term
    assert has_term("ergonomic mesh office chair", "chair") and has_term("office chairs", "chair")
    assert not has_term("backup battery", "back") and not has_term("macbook", "back") and not has_term("steel frame", "tee")
