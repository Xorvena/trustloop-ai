# API

Interactive OpenAPI docs: `http://localhost:8000/docs`. All routes except `/api/auth/*`, `/api/health` and `/api/payments/webhook` require `Authorization: Bearer <jwt>`.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` |
| Agents | `POST/GET /api/agents`, `GET/PATCH /api/agents/{id}`, `GET /api/agents/{id}/trust` |
| Policies | `POST /api/policies/parse` (draft only), `POST/GET /api/policies`, `GET/PATCH /api/policies/{id}`, `GET /api/merchants` |
| Products | `GET /api/products`, `POST /api/products/search` |
| Proposals | `POST/GET /api/proposals`, `GET /api/proposals/{id}`, `POST /api/proposals/{id}/amend` |
| Evaluations | `POST /api/evaluations` (non-persisting what-if), `GET /api/evaluations/{proposal_id}` |
| Approvals | `GET /api/approvals/pending`, `POST /api/approvals/{id}/decision` `{decision: approve|reject}` |
| Payments | `GET /api/payments/config`, `POST /api/payments/create-order` `{proposal_id}`, `POST /api/payments/capture` `{paypal_order_id}`, `POST /api/payments/webhook` |
| Reporting | `GET /api/transactions[?q&state&decision&agent_id&sort&order&limit&offset]`, `GET /api/transactions/{id}`, `GET /api/analytics/{overview,spending,agents}`, `GET /api/audit-logs` |
| Demo/meta | `POST /api/demo/seed`, `GET /api/health` |

Errors: `{ "error": "<code>", "detail": "<message>" }`. Notable codes: `approval_expired` (409), `approval_invalidated` (409), `revalidation_failed` (409, with `failures`), `approval_already_decided` (409), `paypal_not_configured` (503), `verification_failed` (502), `capture_failed` (402/502).

Notes: `/api/proposals` takes only `agent_id` (public code), `product_id`, optional text; amount/merchant come from the catalog. `/api/proposals/{id}/amend` and `/api/evaluations` are additions beyond the original list (needed for scenario 8 and what-if evaluation).
