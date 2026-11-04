# PROJECT_STATUS

_Built in a sandboxed environment with no Gemini key, PayPal credentials, PostgreSQL, browser, or GitHub access. Nothing was pushed._

## Completed (code written + tested where stated)
| Module | Status |
|---|---|
| E Policy engine (all 12 checks, 4 decisions) | Done, unit + API tested |
| State machine, optimistic locking | Done, tested |
| K Audit log (append-only at ORM level) | Done, tested |
| B Agents (CRUD, permissions, revoke, ownership) | Done, tested |
| C Policy builder (Gemini parse → Pydantic → user confirm; regex fallback labelled) | Done; Gemini path tested **with mocked client only** |
| D Shopping agent (intent, deterministic ranking, explanation) | Done; Gemini path mocked-tested only; fallback tested |
| F Risk engine (rules + capped advisory AI signals) | Done, tested (AI mocked) |
| G Prompt-injection defense (no-tool LLM, tagged untrusted data, detector, backend authority) | Done, scenario 10 tested |
| H Trust score (5 weighted components, snapshots, explanations) | Done, tested |
| I Approvals (binding hash, expiry, replay, revalidation) | Done, tested |
| J PayPal (OAuth, Orders v2 create/capture, verification, idempotency, webhook verify+reconcile) | Code done; tested **against a fake PayPal client only**. Never run against real sandbox |
| L Transactions + analytics + CSV export | Done, tested (API); UI built |
| Frontend: 8 screens + login, toasts, modals, skeletons, empty/error states | Builds + typechecks; **never viewed in a browser** |
| Alembic migration `0001` | Verified upgrade/downgrade/check on SQLite; Postgres DDL rendered offline only |

## Tests actually executed
- `pytest` backend: **48 passed**, 0 failed (3 consecutive runs, same result).
- `vitest` frontend: **8 passed**.
- `tsc --noEmit`: clean. `next build`: succeeded (11 routes).
- Live uvicorn smoke test (register → seed → proposal → CORS preflight): worked.

## Could NOT be executed / verified
- Real PayPal Sandbox order creation, JS SDK checkout, capture, webhook signature verification.
- Real Gemini calls; the default model name `gemini-3.5-flash` came from a docs search and is unverified against your key (older 2.5 models were reported as retiring). Change `GEMINI_MODEL` if needed.
- PostgreSQL/Supabase execution, Vercel/Render deployment (no public deployment exists).
- Browser/E2E tests (no Playwright), screenshots, the Devpost rules check, PayPal INR support for your accounts.
- Frontend component tests cover only shared components, not pages.

## Known bugs / rough edges
- Analytics daily chart does not bucket rejected/expired/failed proposals.
- Trust score `POLICY_RULES` contains a vestigial placeholder entry (harmless).
- Agent codes are globally unique.
- Approval Center shows only PENDING approvals; approved-but-unpaid purchases are paid from Transactions detail (or right after approving).
- Amend endpoint has no UI.
- Pending proposals do not reserve budget (revalidated at approval/payment instead).

## Next steps
1. Add credentials; run backend; do one real sandbox purchase end to end (Lite 13). Fix whatever breaks.
2. Configure the webhook (public URL) and test refund/denied events.
3. Point `DATABASE_URL` at Supabase, `alembic upgrade head`, rerun pytest with Postgres.
4. Deploy (Render + Vercel), record screenshots, add Playwright flow test.
5. Verify hackathon rules on Devpost; write the submission text.
