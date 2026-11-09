# PROJECT_STATUS

_Built in a sandbox with no Gemini key, PayPal credentials, PostgreSQL, browser, or internet access to Google/PayPal/DummyJSON. Nothing was pushed._

## Completed modules
| Module | Status |
|---|---|
| Policy engine, state machine, approvals, audit log, agents, risk, trust score, analytics | Done; unchanged logic; all original tests pass |
| PayPal (OAuth, Orders v2, capture verification, idempotency, webhooks) | Code done; tested against a **fake PayPal client only** |
| Search (brand/model/spec verification, matches vs alternatives, honest notes) | Done, tested |
| Curated catalog (36 products) | Done; demo data, not live inventory |
| **Provider layer + DummyJSON demo provider** (~190 products, ~24 categories, real photos) | Done; tested with mock transport + a local stand-in server. **Not tested against the real dummyjson.com** (no access) |
| **Gemini wrapper** | **Root-cause bug fixed** (see below); tested via real SDK against a local fake server |
| Policy Builder UI: labelled interpretation, editable fields, edit saved policies | Done, component-tested |
| Agents UI: category chips + Select all, "Add demo agents" | Done |
| Frontend 8 screens | Builds + typechecks + component tests; **never viewed in a real browser** |
| Alembic 0001 + 0002 | Verified on SQLite; PostgreSQL SQL rendered offline only |

## This iteration (round 4): findings from your screenshots
1. **Chart hover grey box:** Recharts' default tooltip cursor (`#ccc`). Now a subtle tint; the "Decisions per day" chart also gets a legend and a "closed" series (expired/cancelled/rejected/failed), because a day with only such proposals used to render as an empty, misleading column. Verified in a real browser (cursor fill read from the DOM).
2. **PayPal buttons on white:** a light iframe inside a `color-scheme: dark` page is painted opaque white by the browser. The wrapper now declares `color-scheme: light` and the tagline strip is removed. Measured in Chromium: iframe margin pixel (255,255,255) before, card navy after.
3. **"Debit or Credit Card" does nothing:** probable cause was in my code: orders were created with `payment_source.paypal`, which locks an order to the PayPal wallet. Removed (funding-agnostic `application_context` instead). Also: the buttons were re-mounted whenever the parent re-rendered (that can kill an open popup), error text from the SDK was hidden, and there was no way to hide an unavailable funding source (`PAYPAL_DISABLE_FUNDING`). **Not verified against PayPal**: I can't reach it from here, so the card flow is untested. Your first screenshot proves OAuth + order creation + the wallet login work.
4. **Gemini uses the fallback model:** it means the integration works but `gemini-3.8-flash` fails for you. Cause unknown from here; added `GET /api/health/gemini/probe` (latency + classified error per model, plain and structured), a visible explanation on the page, and a per-model cooldown so a failing primary doesn't add retry delay to every search.
5. **Silly "risk signal":** Gemini's advisory text "standard laptop purchase well within the stated budget" was shown as a risk bullet. The prompt now asks for suspicious items only (empty list otherwise) and low-severity AI remarks are dropped.
6. **Provider returned "1 product" for a chair search but only the built-in chair was shown:** the provider's chair has the generic type "furniture". Search now includes same-category products whose name contains the word you used. Also "1 product(s)" pluralisation, and Transactions now has separate Status and Payment columns (AUTHORIZED is a status, not a payment).

## Tests actually executed
- Backend `pytest`: **167 passed, 0 failed** (previous round: 151; originally 48, all still passing).
- Frontend `vitest`: **41 passed**; `tsc --noEmit` clean; `next build` succeeded.
- Real-browser (headless Chromium) checks of the real app: image clipping, the approve-without-paying -> BLOCKED -> cancel -> unblocked flow, chart hover cursor, PayPal container transparency (with a stub iframe: the real PayPal SDK can't load here), transactions table.
- Live uvicorn runs: provider reachable (local stand-in) returned provider products with image URLs, INR prices and `merchant_approved`; provider unreachable returned a clear `network_error` status.

## NOT verified
- A real Gemini call with your key (use `GET /api/health/gemini`). 503/504 handling was tested against a local server that imitates those errors, not against Google itself. The default `gemini-3.8-flash` is confirmed only against the docs' model list.
- The real dummyjson.com API (field names follow its public docs; image host assumed `*.dummyjson.com`, restricted by validation. If photos don't show, check the browser console and the `image_url` host).
- Real PayPal sandbox, PostgreSQL/Supabase execution of migration 0002, deployment, browser/E2E, visual review of the new screens.

## Known limitations
- Provider items are fake products from a fake merchant; prices converted at a demo FX rate; descriptions can be odd. Provider products lack structured specs, so spec filters (RAM, sizes) show them only as alternatives.
- The rule-based parser is heuristic English-only.
- Pending proposals don't reserve budget; amend endpoint has no UI; agent codes are globally unique.
- Existing users must run `alembic upgrade head` (0002) and restart; set `GEMINI_MODEL=gemini-3.8-flash`.

## Next steps
1. Restart the backend; open `/api/health/gemini`; confirm "Generated by Gemini" appears in a search and in Policy Builder.
2. Click **Add demo agents**; search "perfume under 5000" and check photos load (needs internet from the backend).
3. Real PayPal sandbox purchase end to end; webhook with a public URL.
4. If you want real retailer data: pick a partner API you can get keys for (e.g. an affiliate/product-search API) and implement a provider in `backend/app/providers/`.
