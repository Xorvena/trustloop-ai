# Architecture

```
Browser (Next.js) ──JWT──▶ FastAPI ─┬─ shopping agent (Gemini: structured output only, no tools)
                                    ├─ proposal service ─▶ risk engine ─▶ policy engine (deterministic)
                                    ├─ approvals (bound, expiring, replay-protected)
                                    ├─ state machine (optimistic locking)
                                    ├─ payments service ─▶ PayPal Orders v2 (OAuth2, backend only)
                                    └─ audit log (append-only at ORM level)
                                    PostgreSQL / SQLite (SQLAlchemy + Alembic)
```

## Trust boundaries
- **LLM** can: parse a policy *draft*, extract shopping intent, write a summary, add advisory risk hints (capped at +15 points). It can **not**: call tools, edit stored policies, approve, or touch PayPal.
- **Untrusted text**: product descriptions, request text, rationale. Wrapped in explicit data tags for the LLM and scanned by a heuristic injection detector that feeds the risk score.
- **Policy engine** (`app/policies/engine.py`): pure functions over dataclasses; no trust-score input (enforced by a test).
- **Payments** (`app/payments/service.py`): the only code that talks to PayPal. Amount always read from the DB; `create-order` accepts only a proposal id.

## Decision logic
Precedence `BLOCKED > REVIEW > REQUIRES_APPROVAL > APPROVED`.
BLOCK rules: agent identity/ownership, agent active, currency, category, per-agent max, active policy (fail closed), proposal state, budget (committed spend), duplicates, risk ≥ block threshold. REVIEW: merchant not on allowlist, risk ≥ review threshold. APPROVAL: amount > threshold.

## State machine
`PROPOSED → EVALUATED → PENDING_APPROVAL → AUTHORIZED → PAYPAL_ORDER_CREATED → CAPTURED`; terminal `BLOCKED REJECTED EXPIRED FAILED CANCELLED`. `EVALUATED → AUTHORIZED` only with explicit auto-approve. `PENDING_APPROVAL/AUTHORIZED → EVALUATED` exists only for amendments. Concurrent writers hit `version_id_col` → HTTP 409.

## Approvals
Each approval stores a SHA-256 binding over proposal, user, agent, amount, currency, merchant, product and expiry. Any later change breaks the hash → `INVALIDATED`. Decisions are single-use (conditional UPDATE). Auto-approved purchases also receive an `AUTO_APPROVED` authorization record with expiry so payment always requires a valid record. Hard rules are re-run at approval time, order creation and capture.

## Payment flow
create-order (revalidate → convert amount → PayPal `PayPal-Request-Id` idempotent create) → buyer approves in PayPal JS SDK → capture (claim `CREATED→CAPTURING` atomically → PayPal capture → verify id/status/reference/amount/currency against our records → persist Transaction → `CAPTURED`). Duplicate capture returns the stored receipt without calling PayPal. Webhooks: verified through PayPal's verify-webhook-signature API, deduped by event id, can reconcile a capture the browser never reported.

## Database
13 tables: the 11 required plus `trust_snapshots` and `webhook_events`. `Numeric(14,2)` + `Decimal` for money, explicit currency columns, unique constraints on agent code, payment order, capture id, one transaction per proposal.
