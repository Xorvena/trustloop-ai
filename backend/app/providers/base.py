"""Product provider interface. A provider turns an external product source into `ProviderProduct` records, which the
catalog service caches as `Product` rows. The financial policy engine never talks to providers: it only sees the cached
product's price/merchant/category/currency, and revalidation compares against that same row."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol


class ProviderError(Exception):
    """Safe-to-display provider failure. `code`: timeout | network_error | bad_response | http_error | disabled."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class ProviderProduct:
    external_id: str
    name: str
    brand: str
    model: str
    category: str            # permission scope (electronics, clothing, ...)
    product_type: str
    price_inr: Decimal
    description: str
    image_url: str | None
    availability: str        # in_stock | limited_stock | out_of_stock
    merchant: str
    source: str              # e.g. "provider:dummyjson"
    specs: dict = field(default_factory=dict)


class ProductProvider(Protocol):
    name: str
    source: str

    def search(self, query: str, limit: int) -> list[ProviderProduct]: ...
