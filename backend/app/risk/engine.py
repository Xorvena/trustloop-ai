"""Risk intelligence: deterministic signals + optional advisory Gemini signals.

Backend rules decide the action (policy engine consumes only the numeric score + thresholds).
AI signals are capped so they can nudge a score but never single-handedly decide an outcome.
This is a risk heuristic, NOT guaranteed fraud detection.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from app.risk.injection import detect

WEIGHTS = {
    "large_purchase": 15, "repeated_attempts": 20, "duplicate_purchase": 25, "unapproved_merchant": 20,
    "high_frequency": 20, "out_of_scope": 30, "inactive_agent": 30, "prompt_injection": 40,
}
AI_CAP = 15  # max points Gemini-derived signals can add in total


@dataclass
class RiskInputs:
    amount: Decimal
    agent_max_transaction: Decimal
    approval_threshold: Decimal
    merchant_approved: bool
    duplicate_exists: bool
    agent_active: bool
    category_permitted: bool
    recent_attempts_same_product: int
    recent_attempts_agent: int
    frequency_limit: int
    untrusted_texts: list[str] = field(default_factory=list)  # product description, request, rationale


@dataclass
class RiskResult:
    score: int
    level: str
    signals: list[dict]
    ai_signals: list[dict]
    ai_used: bool


def level_for(score: int) -> str:
    return "low" if score < 30 else "medium" if score < 60 else "high" if score < 80 else "critical"


def assess(inp: RiskInputs, ai_signals: list[dict] | None = None) -> RiskResult:
    sig: list[dict] = []

    def add(code: str, detail: str) -> None:
        sig.append({"code": code, "points": WEIGHTS[code], "detail": detail, "source": "deterministic"})

    if inp.agent_max_transaction > 0 and inp.amount >= inp.agent_max_transaction * Decimal("0.8"):
        add("large_purchase", f"Amount is >= 80% of the agent's max transaction ({inp.agent_max_transaction}).")
    elif inp.amount >= inp.approval_threshold * 2:
        add("large_purchase", "Amount is at least 2x the approval threshold.")
    if inp.recent_attempts_same_product >= 2:
        add("repeated_attempts", f"{inp.recent_attempts_same_product} recent attempts for the same product.")
    if inp.duplicate_exists:
        add("duplicate_purchase", "Product already purchased or in flight.")
    if not inp.merchant_approved:
        add("unapproved_merchant", "Merchant is not on the approved list.")
    if inp.recent_attempts_agent > inp.frequency_limit:
        add("high_frequency", f"{inp.recent_attempts_agent} proposals in window (limit {inp.frequency_limit}).")
    if not inp.category_permitted:
        add("out_of_scope", "Agent attempted a category outside its permissions.")
    if not inp.agent_active:
        add("inactive_agent", "Agent is not active.")
    hits = sorted({h for t in inp.untrusted_texts for h in detect(t)})
    if hits:
        add("prompt_injection", f"Untrusted text matched injection patterns: {', '.join(hits)}. Content was ignored as instructions.")

    clean_ai: list[dict] = []
    for s in (ai_signals or [])[:5]:
        if isinstance(s, dict) and s.get("signal"):
            sev = s.get("severity") if s.get("severity") in ("low", "medium", "high") else "low"
            clean_ai.append({"code": str(s["signal"])[:60], "severity": sev, "detail": str(s.get("explanation", ""))[:300],
                             "points": {"low": 2, "medium": 5, "high": 8}[sev], "source": "gemini_advisory"})
    ai_points = min(AI_CAP, sum(s["points"] for s in clean_ai))
    score = min(100, sum(s["points"] for s in sig) + ai_points)
    return RiskResult(score=score, level=level_for(score), signals=sig, ai_signals=clean_ai, ai_used=bool(ai_signals is not None))
