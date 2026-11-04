# TRUSTLOOP AI

> **Let AI buy. Let humans stay in control.**

TRUSTLOOP AI is a governance and authorization layer between autonomous AI shopping agents and PayPal. Agents research and *propose*; a deterministic backend policy engine decides; humans approve what needs approving; only the trusted backend can create and capture PayPal Sandbox orders. Every step is audited.

**Status:** working MVP, built and tested in a sandbox without Gemini/PayPal/PostgreSQL credentials. See [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for exactly what was and was not verified. **Live PayPal and Gemini calls have not been exercised yet; do that first (steps below).**

## Architecture in one paragraph
`Next.js UI → FastAPI → { policy engine (pure Python) · risk engine · approvals · state machine · audit log } → PayPal Orders v2`. Gemini is used only for structured output (policy parsing, intent extraction, summaries, advisory risk signals) with **no tools registered**, and its output is Pydantic-validated and never applied automatically. See [`docs/architecture.md`](docs/architecture.md) and [`docs/security.md`](docs/security.md).

## Quick start (Windows PowerShell)
Prerequisites: Python 3.11+, Node 20+.

```powershell
# 1) Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
Copy-Item ..\.env.example .env        # then edit .env (JWT_SECRET is required)
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into JWT_SECRET
alembic upgrade head                  # creates tables (works for SQLite and PostgreSQL)
uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/docs

# 2) Frontend (new terminal)
cd frontend
"NEXT_PUBLIC_API_URL=http://localhost:8000" | Out-File -Encoding ascii .env.local
npm install
npm run dev                           # http://localhost:3000
```
The backend starts without Gemini or PayPal credentials; those features show clear "not configured" messages. Without a Gemini key the policy parser uses a labelled regex fallback.

On first login click **Create demo setup** on the dashboard (creates the ₹75,000 / ₹25,000 policy, three approved merchants and three labelled `[DEMO]` agents).

## Credentials you must supply
| Variable | Where to get it |
|---|---|
| `JWT_SECRET` | generate locally (command above) |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Google AI Studio. Verify the model name works for your key. |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | PayPal Developer Dashboard → Sandbox app |
| `PAYPAL_WEBHOOK_ID` | Sandbox app → add webhook → `https://<public-backend>/api/payments/webhook`; events: `PAYMENT.CAPTURE.COMPLETED/DENIED/REFUNDED/REVERSED`. Needs a public URL (use the Render deploy or a tunnel). |
| `DATABASE_URL` | Supabase → Project Settings → Database → connection string (optional; SQLite works locally) |

Use a Sandbox **buyer** account to approve checkout. No real money moves.

> **Currency:** PayPal may not settle INR for every account. Orders are created in `PAYPAL_CURRENCY` (default USD), converted server-side from the authoritative DB amount at a fixed **demo** rate (`INR_PER_UNIT_PAYPAL_CURRENCY`). Set `PAYPAL_CURRENCY=INR` if your sandbox accounts support it.

## Tests
```powershell
cd backend;  pytest -q          # 48 tests: engine, 10 scenarios, security, mocked Gemini/PayPal
cd frontend; npm test           # 8 component/util tests
cd frontend; npm run typecheck; npm run build
```
External services are mocked **only inside tests**.

## Demo scenarios (all automated in `backend/tests/test_scenarios.py`)
1 ₹15,000 → APPROVED · 2 ₹30k+ → REQUIRES_APPROVAL · 3 ₹80k+ → BLOCKED · 4 inactive agent → BLOCKED · 5 duplicate → BLOCKED · 6 unapproved merchant → REVIEW · 7 expired approval → payment rejected · 8 changed amount → approval invalidated · 9 repeated capture → single capture · 10 prompt-injection product → still policy-evaluated. Manual script: [`docs/demo-script.md`](docs/demo-script.md).

## Deployment (not yet performed)
Supabase (Postgres) → set `DATABASE_URL`, run `alembic upgrade head` once. Render: root `backend`, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, set env vars, `CORS_ORIGINS=<vercel url>`. Vercel: root `frontend`, env `NEXT_PUBLIC_API_URL=<render url>`.

## Stack
Next.js 14 (App Router) · React 18 · TypeScript · Tailwind · shadcn/ui-style primitives (hand-written with Radix + CVA, not CLI-generated) · Lucide · Recharts · FastAPI · Pydantic · SQLAlchemy · Alembic · HTTPX · PostgreSQL/SQLite · `google-genai` · PayPal Orders v2.
