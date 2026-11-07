"""Fetches products from enabled providers and caches them as `Product` rows (so proposals, approval binding and payment
revalidation all use one authoritative DB price). Provider failures never break search: they are reported to the UI."""
import logging
import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Product
from app.providers.base import ProductProvider, ProviderError, ProviderProduct
from app.providers.dummyjson import DummyJsonProvider

log = logging.getLogger("trustloop.providers")
_CACHE_TTL = 300.0
_cache: dict[tuple[str, str], tuple[float, list[ProviderProduct]]] = {}


def build_providers() -> list[ProductProvider]:
    """Providers enabled by PRODUCT_PROVIDERS (besides the built-in 'curated' catalog). Tests monkeypatch this."""
    out: list[ProductProvider] = []
    for name in get_settings().enabled_providers:
        if name == "dummyjson":
            out.append(DummyJsonProvider())
    return out


def clear_cache() -> None:
    _cache.clear()


def upsert(db: Session, items: list[ProviderProduct]) -> int:
    """Insert/update provider products by SKU. Returns the number of NEW rows."""
    if not items:
        return 0
    prefix = items[0].source.split(":", 1)[-1]
    skus = {f"{prefix}-{i.external_id}": i for i in items}
    existing = {p.sku: p for p in db.scalars(select(Product).where(Product.sku.in_(list(skus))))}
    added = 0
    for sku, i in skus.items():
        fields = dict(name=i.name, brand=i.brand, model=i.model, merchant=i.merchant, category=i.category, product_type=i.product_type,
                      price=Decimal(i.price_inr), currency="INR", description=i.description, specs=i.specs, availability=i.availability,
                      image_url=i.image_url, image_source="provider_photo" if i.image_url else None, source=i.source)
        row = existing.get(sku)
        if row is None:
            db.add(Product(sku=sku, **fields))
            added += 1
        else:
            for k, v in fields.items():
                setattr(row, k, v)
    db.commit()
    return added


def refresh(db: Session, queries: list[str]) -> list[dict]:
    """Query every enabled provider for each query, cache results in the DB, and return per-provider status."""
    statuses: list[dict] = []
    limit = get_settings().provider_max_results
    try:
        providers = build_providers()
    except Exception as exc:  # misconfiguration must not break search
        log.warning("provider setup failed: %s", type(exc).__name__)
        return [{"provider": "unknown", "ok": False, "count": 0, "code": "setup_error", "message": "Product provider could not be initialised."}]
    for prov in providers:
        found: dict[str, ProviderProduct] = {}
        error: ProviderError | None = None
        for q in queries:
            key = (prov.name, q.lower())
            hit = _cache.get(key)
            if hit and time.time() - hit[0] < _CACHE_TTL:
                items = hit[1]
            else:
                try:
                    items = prov.search(q, limit)
                except ProviderError as exc:
                    error = exc
                    log.warning("provider %s query=%r failed code=%s", prov.name, q, exc.code)
                    continue
                _cache[key] = (time.time(), items)
            for i in items:
                found[i.external_id] = i
        new = upsert(db, list(found.values())) if found else 0
        statuses.append({"provider": prov.name, "ok": error is None or bool(found), "count": len(found), "new_products": new,
                         "code": error.code if error else None,
                         "message": (error.message if error else None) if not found else (f"Partial results: {error.message}" if error else None)})
    return statuses
