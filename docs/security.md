# Security notes

## Implemented
Backend-only PayPal credentials · bcrypt password hashing · JWT auth with ownership checks on every resource (foreign IDs return 404) · Pydantic validation on all inputs · ORM-only SQL · CORS allow-list · in-memory rate limits on auth, parse, search, proposals, decisions and payments · generic 500 responses · webhook signature verification (refuses all webhooks if `PAYPAL_WEBHOOK_ID` is unset) · idempotent order/capture · approval expiry, binding and replay protection · fail-closed policy · prompt-injection tripwire + no-tool LLM · append-only audit log (ORM hooks raise on UPDATE/DELETE).

## Known limitations (hackathon MVP; do not call this production-grade)
1. JWT is stored in `localStorage` (XSS-exposed). Production should use httpOnly cookies + CSRF protection.
2. Rate limiter is per-process memory; use Redis for multiple instances.
3. Audit log is append-only only at application level. A DB superuser can alter it; there is no hash chain or signing. Do not claim immutability.
4. Injection detection is heuristic and can be evaded; the real protection is architectural (no LLM authority).
5. Risk scoring is a heuristic, not fraud detection.
6. Catalog is static demo data; no live retailer verification.
7. INR→USD uses a fixed demo rate, not live FX.
8. No email verification, MFA, password reset, or account lockout.
9. Webhook verification and PayPal flows are implemented per PayPal docs but were **not** exercised against live sandbox in the build environment.
10. SQLite concurrency tests do not prove behaviour under PostgreSQL row-locking; the code relies on conditional UPDATEs and optimistic versioning, which are portable, but verify on Postgres.
11. Agent codes are globally unique (a user can see "already exists" for another user's code).
