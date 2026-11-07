"""DummyJSON provider (https://dummyjson.com): a free demo REST API with ~190 sample products and real product images.

It is DEMO data (fake store, USD prices, no real inventory): good for exercising the full agent flow across many
categories with realistic images. It is not a real retailer. Prices are converted to INR with a configurable DEMO rate.
Endpoints used: GET /products/search?q=&limit=  (envelope: {products: [...], total, skip, limit}).
"""
import re
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.providers.base import ProviderError, ProviderProduct

SOURCE = "provider:dummyjson"
MERCHANT = "DummyJSON Demo Store"

# provider category slug -> (our category, product_type, search synonyms)
CATEGORY_MAP: dict[str, tuple[str, str, list[str]]] = {
    "laptops": ("electronics", "laptop", []),
    "smartphones": ("electronics", "smartphone", []),
    "tablets": ("electronics", "tablet", ["tablet", "tablets", "ipad"]),
    "mobile-accessories": ("electronics", "mobile_accessory", ["mobile accessory", "phone accessory", "charger", "power bank", "phone case", "earphones case"]),
    "mens-shirts": ("clothing", "shirt", ["shirt", "shirts"]),
    "womens-dresses": ("clothing", "dress", ["dress", "dresses", "gown"]),
    "tops": ("clothing", "top", ["tops", "blouse"]),
    "mens-shoes": ("footwear", "shoes", []),
    "womens-shoes": ("footwear", "shoes", []),
    "womens-bags": ("accessories", "bag", ["bag", "bags", "handbag", "purse"]),
    "womens-jewellery": ("accessories", "jewellery", ["jewellery", "jewelry", "necklace", "earrings", "bracelet"]),
    "mens-watches": ("accessories", "watch", ["watch", "watches", "wristwatch"]),
    "womens-watches": ("accessories", "watch", []),
    "sunglasses": ("accessories", "sunglasses", ["sunglasses", "shades"]),
    "beauty": ("beauty", "makeup", ["makeup", "lipstick", "mascara", "eyeshadow", "nail polish", "beauty"]),
    "skin-care": ("beauty", "skincare", ["skincare", "skin care", "moisturizer", "moisturiser", "serum", "face cream"]),
    "fragrances": ("beauty", "fragrance", ["perfume", "fragrance", "cologne", "attar", "deodorant"]),
    "furniture": ("furniture", "furniture", ["furniture", "sofa", "couch", "bed", "table", "wardrobe", "cabinet", "shelf"]),
    "home-decoration": ("home", "home_decor", ["home decor", "decor", "lamp", "vase", "candle", "plant", "wall art"]),
    "kitchen-accessories": ("home", "kitchen_accessory", ["kitchen", "utensil", "utensils", "cookware", "spatula", "knife"]),
    "groceries": ("groceries", "grocery", ["grocery", "groceries", "food", "vegetables", "fruit", "fruits", "juice", "snack"]),
    "sports-accessories": ("sports", "sports_item", ["sports", "cricket", "football", "basketball", "tennis", "golf", "baseball"]),
    "motorcycle": ("automotive", "motorcycle", ["motorcycle", "bike", "scooter"]),
    "vehicle": ("automotive", "vehicle", ["vehicle", "car"]),
}
# extra product types (beyond the curated ones) the search parser can recognise, with their synonyms
PROVIDER_TYPE_SYNONYMS: dict[str, list[str]] = {}
for _slug, (_cat, _type, _syn) in CATEGORY_MAP.items():
    if _syn:
        PROVIDER_TYPE_SYNONYMS.setdefault(_type, [])
        PROVIDER_TYPE_SYNONYMS[_type] += [s for s in _syn if s not in PROVIDER_TYPE_SYNONYMS[_type]]
PROVIDER_TYPE_TO_CATEGORY = {t: c for c, t, _ in CATEGORY_MAP.values()}
PROVIDER_CATEGORIES = sorted({c for c, _, _ in CATEGORY_MAP.values()})
_ALLOWED_IMAGE_SUFFIX = ".dummyjson.com"


def safe_image_url(url: object) -> str | None:
    """Only accept plain https URLs on dummyjson.com hosts. Anything else (data:, javascript:, other hosts) is dropped."""
    if not isinstance(url, str) or len(url) > 500:
        return None
    u = urlparse(url)
    host = (u.hostname or "").lower()
    return url if u.scheme == "https" and (host == "dummyjson.com" or host.endswith(_ALLOWED_IMAGE_SUFFIX)) else None


def _availability(item: dict) -> str:
    status = str(item.get("availabilityStatus", "")).lower()
    if "out" in status:
        return "out_of_stock"
    if "low" in status:
        return "limited_stock"
    if status:
        return "in_stock"
    stock = item.get("stock")
    return "in_stock" if isinstance(stock, (int, float)) and stock > 10 else "limited_stock" if isinstance(stock, (int, float)) and stock > 0 else "out_of_stock"


def _clean(text: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def map_item(item: dict, usd_to_inr: Decimal) -> ProviderProduct | None:
    """Convert one DummyJSON product to a ProviderProduct. Returns None for malformed items (never raises)."""
    try:
        pid, title = item["id"], _clean(item["title"], 200)
        price = Decimal(str(item["price"]))
        if not title or price <= 0:
            return None
    except (KeyError, ArithmeticError, ValueError, TypeError):
        return None
    slug = str(item.get("category", ""))
    category, ptype, _ = CATEGORY_MAP.get(slug, ("other", slug.replace("-", "_") or "other", []))
    brand = _clean(item.get("brand"), 80)
    model = title[len(brand):].strip(" -") if brand and title.lower().startswith(brand.lower()) else title
    thumb = safe_image_url(item.get("thumbnail")) or safe_image_url((item.get("images") or [None])[0])
    specs = {k: v for k, v in {
        "rating": item.get("rating"), "tags": [str(t)[:30] for t in (item.get("tags") or [])][:6], "weight": item.get("weight"),
        "warranty": _clean(item.get("warrantyInformation"), 80) or None, "shipping": _clean(item.get("shippingInformation"), 80) or None,
        "return_policy": _clean(item.get("returnPolicy"), 80) or None, "provider_category": slug,
    }.items() if v not in (None, "", [])}
    return ProviderProduct(
        external_id=str(pid), name=title, brand=brand, model=_clean(model, 120) or title, category=category, product_type=ptype,
        price_inr=(price * usd_to_inr).quantize(Decimal("0.01"), ROUND_HALF_UP), description=_clean(item.get("description"), 1000),
        image_url=thumb, availability=_availability(item), merchant=MERCHANT, source=SOURCE, specs=specs)


class DummyJsonProvider:
    name = "dummyjson"
    source = SOURCE

    def __init__(self, transport: httpx.BaseTransport | None = None):
        s = get_settings()
        self._usd_to_inr = s.provider_usd_to_inr
        self._http = httpx.Client(base_url=s.dummyjson_base_url, timeout=s.provider_timeout_seconds, transport=transport,
                                  headers={"Accept": "application/json", "User-Agent": "trustloop-ai/0.1 (hackathon demo)"})

    def search(self, query: str, limit: int = 20) -> list[ProviderProduct]:
        q = re.sub(r"[^\w\s\-']", " ", query).strip()[:80]
        if not q:
            return []
        try:
            r = self._http.get("/products/search", params={"q": q, "limit": min(max(limit, 1), 50)})
        except httpx.TimeoutException:
            raise ProviderError("timeout", "The product provider timed out.") from None
        except httpx.HTTPError as exc:
            raise ProviderError("network_error", f"Could not reach the product provider ({type(exc).__name__}).") from None
        if r.status_code != 200:
            raise ProviderError("http_error", f"The product provider returned HTTP {r.status_code}.")
        try:
            items = r.json()["products"]
            assert isinstance(items, list)
        except Exception:
            raise ProviderError("bad_response", "The product provider returned an unexpected response.") from None
        return [p for p in (map_item(i, self._usd_to_inr) for i in items if isinstance(i, dict)) if p]
