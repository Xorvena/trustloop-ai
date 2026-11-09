# API

Interactive OpenAPI docs: `http://localhost:8000/docs`. All routes except `/api/auth/*`, `/api/health` and `/api/payments/webhook` require `Authorization: Bearer <jwt>`.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` |
| Agents | `POST/GET /api/agents`, `GET/PATCH /api/agents/{id}`, `GET /api/agents/{id}/trust` |
| Policies | `POST /api/policies/parse` (draft only), `POST/GET /api/policies`, `GET/PATCH /api/policies/{id}`, `GET /api/merchants` |
| Products | `GET /api/products[?category&product_type&brand]`, `GET /api/products/categories`, `POST /api/products/search` |
| Proposals | `POST/GET /api/proposals`, `GET /api/proposals/{id}`, `POST /api/proposals/{id}/amend`, `POST /api/proposals/{id}/cancel` (unpaid only; frees budget) |
| Budget | `GET /api/budget` (used/remaining + the proposals holding it) |
| Evaluations | `POST /api/evaluations` (non-persisting what-if), `GET /api/evaluations/{proposal_id}` |
| Approvals | `GET /api/approvals/pending`, `POST /api/approvals/{id}/decision` `{decision: approve|reject}` |
| Payments | `GET /api/payments/config`, `POST /api/payments/create-order` `{proposal_id}`, `POST /api/payments/capture` `{paypal_order_id}`, `POST /api/payments/webhook` |
| Reporting | `GET /api/transactions[?q&state&decision&agent_id&sort&order&limit&offset]`, `GET /api/transactions/{id}`, `GET /api/analytics/{overview,spending,agents}`, `GET /api/audit-logs` |
| Merchants | `GET /api/merchants`, `POST /api/merchants {name}` (user-initiated allowlist add, audited, idempotent) |
| Demo/meta | `POST /api/demo/seed`, `POST /api/demo/agents` (add missing demo agents), `GET /api/health`, `GET /api/health/gemini` (auth; checks the configured model exists for your key, no generation), `GET /api/health/gemini/probe[?models=a,b]` (auth, 3/min; tiny plain + structured request per model with latency and classified errors) |

Errors: `{ "error": "<code>", "detail": "<message>" }`. Notable codes: `approval_expired` (409), `approval_invalidated` (409), `revalidation_failed` (409, with `failures`), `approval_already_decided` (409), `paypal_not_configured` (503), `verification_failed` (502), `capture_failed` (402/502).

Notes: `/api/proposals` takes only `agent_id` (public code), `product_id`, optional text; amount/merchant come from the catalog. `/api/proposals/{id}/amend` and `/api/evaluations` are additions beyond the original list (needed for scenario 8 and what-if evaluation).

## Product and search schema
`Product`: `id, sku, name, brand, model, merchant, category, product_type, price, currency, description, specs{}, availability (in_stock|limited_stock|out_of_stock), image_url|null, image_source ("illustration"|"licensed_photo"|null), source`.

`POST /api/products/search {query}` returns:
`status` (`matches_found|no_exact_match|nothing_found`), `requirements`, `interpreted_as[]`, `unverifiable_terms[]`, `notes[]` (e.g. "'ASUS VivobookX16' isn't in the catalog."), `matches[]`, `alternatives[]` (each result has `checks[]`, `unmet[]`, `relation`, `kind`), `results[]` (matches then alternatives, backward compatible), and provenance fields:
`summary`, `summary_source` (`gemini|template`), `summary_model`, `summary_fallback_reason`, `summary_fallback_message`, `intent_source` (`gemini|heuristic`), `intent_model`, `intent_fallback_reason`, `intent_notes[]`.
Fallback reasons: `not_configured, model_not_found, invalid_api_key, permission_denied, rate_limited, upstream_error, network_error, bad_request, bad_output, contradicted_results, unknown_error`.

`POST /api/proposals` returns `409 product_unavailable` for out-of-stock products. Approval items now include `image_url`/`image_source`.

Search response additions: `provider_status[]` (`{provider, ok, count, new_products, code, message}`), per result `merchant_approved`, `unconfirmed_terms[]`. `GET /api/products/categories` now includes provider categories. `POST /api/policies/parse` returns `source` (`gemini|heuristic_fallback`), `model`, `fallback_reason`, `fallback_message` (it falls back to the rule-based parser, labelled, when Gemini fails).

Search/parse responses also include `summary_used_fallback_model`, `intent_used_fallback_model` / `used_fallback_model`: true when `GEMINI_FALLBACK_MODEL` answered (the `*_model` field always names the model that actually answered). New Gemini fallback reason: `recently_unavailable` (call skipped by the circuit breaker).

`POST /api/products/search` also returns `gemini_status` (`primary_model`, `fallback_model`, `primary_cooling_down_seconds`, `primary_last_failure{code,message,seconds_ago}`) when Gemini is configured. `GET /api/payments/config` includes `disable_funding`. `GET /api/analytics/spending` daily rows include `closed` (rejected/expired/cancelled/failed).
