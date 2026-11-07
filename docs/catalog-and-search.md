# Catalog and search

## What the catalog is (and isn't)
A hand-curated, static set of 36 products in `backend/app/agents/catalog.py`, upserted into the `products` table at startup. **It is not live retailer inventory.** Prices, specs and availability are illustrative. Ten original SKUs (used by the automated demo scenarios) use fictional brands and kept their original prices; the remainder use real brand/model names with illustrative data. Nothing here verifies a real retailer's stock or price.

## Categories vs product types
`category` is the permission scope an agent is granted: `electronics, clothing, footwear, books, furniture`. `product_type` is the finer kind (`laptop, smartphone, headphones, keyboard, monitor, tshirt, jeans, hoodie, jacket, kurta, shoes, book, chair`) and decides which attributes apply (`TYPE_ATTRIBUTES`). Search only applies filters that make sense for the type (no RAM filter on shoes). The policy engine's `category_permission` rule is unchanged and still blocks out-of-scope purchases.

## Search pipeline (`backend/app/agents/shopping.py`)
1. **Understand**: Gemini (structured output, no tools) if configured, else the rule-based parser. Gemini output is guarded: a brand/model/author not present in the user's words is discarded, and anything the rule parser found that Gemini omitted is added back. Result source and any fallback reason are returned to the UI.
2. **Verify**: every stated requirement becomes a check per product (brand, model relation `exact|contains|same_line`, budget, RAM, storage, battery, size, colour, gender, material, shoe type, author, genre, language, availability, plus catalog-text keywords).
3. **Classify**: *match* = all checks pass; *alternative* = anything else, with `unmet[]`. The two closest alternatives are always shown, then diverse trade-offs. Unrelated out-of-stock items are omitted.
4. **Notes**: brand/model/requirements that nothing satisfies are stated plainly. Terms that can't be mapped or found in the catalog are `unverifiable_terms` (shown, not blocking).
5. **Summarise**: Gemini if available, but rejected if it claims "meets all" when status isn't `matches_found`; otherwise a deterministic template. The response always says which one produced it.

## Images
`image_url` + `image_source`. Bundled files are original generic illustrations (`image_source="illustration"`), not photos. The UI tags them and falls back to a placeholder on null/failed images. No third-party image URLs are included.

## Product providers (implemented: DummyJSON demo provider)
`backend/app/providers/`: `base.py` (interface + `ProviderError`), `dummyjson.py` (mapping/validation), `service.py` (query, TTL cache, upsert, status).
- Search first understands the request, then asks each enabled provider for up to 3 queries (brand+model, the user's own product word, leftover keywords), upserts results into `products` (`sku=dummyjson-<id>`, `source=provider:dummyjson`), and searches the combined set with the same verification pipeline.
- Provider failures never break search: `provider_status[]` reports `ok/code/message` and the UI shows it.
- Provider data is untrusted: strings are length-limited and whitespace-normalised, malformed items are skipped, image URLs must be `https` on `*.dummyjson.com` (anything else is dropped), descriptions still pass through the prompt-injection detector.
- Prices: USD x `PROVIDER_USD_TO_INR` (demo FX). Keep it equal to `INR_PER_UNIT_PAYPAL_CURRENCY` so the PayPal charge equals the provider's USD price.
- Provider products lack structured specs (no RAM/size lists), so spec filters on them show "not listed in the product data" and they appear as alternatives rather than false matches.
- **DummyJSON is a fake store.** It demonstrates breadth and real photos; it does not represent real retailers.

## Descriptive words vs hard requirements
Words that can't be mapped to a field (e.g. "ergonomic", "armrests") become hard checks only for title-style searches with no type/brand/model (e.g. a book title). Next to a type/brand/model they are shown per product as "Not confirmed in product details" and in `unverifiable_terms`; they never silently filter results.

## Next: real retailer data (not implemented)
A provider interface that returns `Product`-shaped records (same fields) from a real product API, with caching and an explicit `source`. The policy engine only sees price, merchant, category and currency, so it needs no change. Open questions: which provider/key, price/stock freshness vs. the approval TTL, and how live price drift interacts with approval binding (already invalidates on change).
