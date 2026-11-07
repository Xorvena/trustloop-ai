# Three-minute demo script (manual, needs Gemini + PayPal Sandbox credentials)

Prep: backend + frontend running, sandbox buyer account ready, `PAYPAL_*` and `GEMINI_API_KEY` set, a fresh user with **Create demo setup** clicked.

| Time | Do | Say |
|---|---|---|
| 0:00–0:25 | Command Center | "AI agents can already buy things. Who controls what they spend?" |
| 0:25–0:55 | Policy Builder: paste the example rules → Interpret → show structured preview → Confirm | "Plain language in, validated JSON out. AI drafts, I confirm, the backend enforces." |
| 0:55–1:25 | AI Shopping: run the laptop request; show ranking and the flagged malicious listing | "Ranking is deterministic; the poisoned description is treated as untrusted data." |
| 1:25–2:05 | Propose Wave headphones (₹15,000 → APPROVED), Lite 13 (₹31,990 → needs approval), Titan 16 (₹82,990 → BLOCKED); show rule-by-rule checks | "Every decision is explainable and made by deterministic code." |
| 2:05–2:35 | Approval Center → Approve Lite 13 → PayPal Sandbox checkout → capture | "Approval is bound to the exact amount and merchant; the backend recomputes and verifies the capture." |
| 2:35–3:00 | Transactions detail, Audit Log, Trust Center | "Autonomy with governance and accountability." |

Reproducible without credentials: `pytest backend/tests/test_scenarios.py -v` runs all ten scenarios (PayPal mocked in tests only).
Verify prizes/rules on the official Devpost page yourself; they were not checked here.
