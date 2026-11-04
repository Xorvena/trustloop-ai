"""Transparent Agent Trust Score (0-100) computed from measurable history.

Weights: policy compliance 35, permission compliance 25, transaction reliability 20,
duplicate-attempt history 10, suspicious-behaviour history 10.
Each component is a smoothed success rate (prior 0.7 with weight 3 pseudo-observations) so new agents
start neutral rather than perfect. The score is informational ONLY: the policy engine takes no trust input.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PurchaseProposal, TrustSnapshot, Agent

WEIGHTS = {"policy_compliance": 35, "permission_compliance": 25, "transaction_reliability": 20,
           "duplicate_history": 10, "suspicious_history": 10}
PRIOR, PRIOR_WEIGHT = 0.7, 3
PERMISSION_RULES = {"agent_identity", "agent_active", "category_permission", "max_transaction", "agent_currency_scope"}
POLICY_RULES = {"budget_remaining", "policy_valid", "policy_currency", "merchant_allowlist", "approval_threshold_ignored"}
LABELS = {
    "policy_compliance": "Share of proposals that did not violate budget/merchant/policy rules",
    "permission_compliance": "Share of proposals within the agent's permissions (status, category, limits)",
    "transaction_reliability": "Share of authorized purchases that completed (vs failed/expired)",
    "duplicate_history": "Share of proposals that were not duplicate attempts",
    "suspicious_history": "Share of proposals without high risk or prompt-injection signals",
}


def _smooth(good: int, total: int) -> float:
    return (good + PRIOR * PRIOR_WEIGHT) / (total + PRIOR_WEIGHT)


def compute(db: Session, agent: Agent) -> dict:
    props = db.scalars(select(PurchaseProposal).where(PurchaseProposal.agent_id == agent.id)).all()
    n = len(props)

    def failed_rules(p) -> set[str]:
        return {c["rule"] for c in (p.decision_explanation or {}).get("checks", []) if not c["passed"]}

    perm_bad = sum(1 for p in props if failed_rules(p) & PERMISSION_RULES)
    pol_bad = sum(1 for p in props if failed_rules(p) & (POLICY_RULES - {"approval_threshold_ignored"}))
    dup_bad = sum(1 for p in props if "duplicate_purchase" in failed_rules(p))
    sus_bad = sum(1 for p in props if p.risk and (p.risk.level in ("high", "critical")
                  or any(s["code"] == "prompt_injection" for s in p.risk.signals)))
    attempted = [p for p in props if p.state in ("CAPTURED", "FAILED", "EXPIRED", "PAYPAL_ORDER_CREATED")]
    rel_bad = sum(1 for p in attempted if p.state in ("FAILED", "EXPIRED"))

    raw = {
        "policy_compliance": (_smooth(n - pol_bad, n), n - pol_bad, n),
        "permission_compliance": (_smooth(n - perm_bad, n), n - perm_bad, n),
        "transaction_reliability": (_smooth(len(attempted) - rel_bad, len(attempted)), len(attempted) - rel_bad, len(attempted)),
        "duplicate_history": (_smooth(n - dup_bad, n), n - dup_bad, n),
        "suspicious_history": (_smooth(n - sus_bad, n), n - sus_bad, n),
    }
    components = {}
    total = 0.0
    for k, (rate, good, obs) in raw.items():
        pts = rate * WEIGHTS[k]
        total += pts
        components[k] = {"weight": WEIGHTS[k], "rate": round(rate, 3), "points": round(pts, 1),
                         "observations": obs, "good": good, "description": LABELS[k]}
    return {"score": round(total), "components": components, "proposals_observed": n,
            "note": "Informational only. A high trust score never overrides limits, permissions, approvals or blocks."}


def snapshot(db: Session, agent: Agent, reason: str) -> dict:
    result = compute(db, agent)
    prev = db.scalars(select(TrustSnapshot).where(TrustSnapshot.agent_id == agent.id)
                      .order_by(TrustSnapshot.created_at.desc())).first()
    explain = reason
    if prev:
        diffs = [f"{k} {result['components'][k]['points'] - prev.components.get(k, {}).get('points', 0):+.1f}"
                 for k in result["components"] if abs(result['components'][k]['points'] - prev.components.get(k, {}).get('points', 0)) >= 0.05]
        explain = f"{reason} (score {prev.score} -> {result['score']}; {', '.join(diffs) or 'no component change'})"
    db.add(TrustSnapshot(agent_id=agent.id, score=result["score"], components=result["components"], reason=explain))
    db.flush()
    return result
