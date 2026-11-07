import inspect
from decimal import Decimal as D

from app.policies import engine as e
from app.services.state_machine import ALLOWED, InvalidTransition, transition
from app.models import ProposalState as S

AGENT = e.AgentFacts(True, True, "active", D("75000"), "INR", ("electronics",))
POLICY = e.PolicyFacts(True, "INR", D("75000"), D("25000"), True, True)
CTX = e.ContextFacts(D("0"), frozenset({"TechMart India"}), False, 0)


def prop(amount, merchant="TechMart India", category="electronics"):
    return e.ProposalFacts(D(amount), "INR", merchant, category, "p1")


def test_decisions_basic():
    assert e.evaluate(AGENT, POLICY, prop("15000"), CTX).decision == "APPROVED"
    assert e.evaluate(AGENT, POLICY, prop("30000"), CTX).decision == "REQUIRES_APPROVAL"
    assert e.evaluate(AGENT, POLICY, prop("80000"), CTX).decision == "BLOCKED"
    assert e.evaluate(AGENT, POLICY, prop("15000", merchant="Unknown"), CTX).decision == "REVIEW"


def test_threshold_boundary_is_inclusive_for_auto_approval():
    assert e.evaluate(AGENT, POLICY, prop("25000"), CTX).decision == "APPROVED"
    assert e.evaluate(AGENT, POLICY, prop("25000.01"), CTX).decision == "REQUIRES_APPROVAL"


def test_precedence_block_beats_review_and_approval():
    ev = e.evaluate(AGENT, POLICY, prop("80000", merchant="Unknown"), CTX)
    assert ev.decision == "BLOCKED"


def test_budget_uses_committed_spend():
    ctx = e.ContextFacts(D("70000"), frozenset({"TechMart India"}), False, 0)
    assert e.evaluate(AGENT, POLICY, prop("10000"), ctx).decision == "BLOCKED"


def test_inactive_wrong_category_duplicate_nopolicy():
    inactive = e.AgentFacts(True, True, "inactive", D("75000"), "INR", ("electronics",))
    assert e.evaluate(inactive, POLICY, prop("1000"), CTX).decision == "BLOCKED"
    assert e.evaluate(AGENT, POLICY, prop("1000", category="furniture"), CTX).decision == "BLOCKED"
    dup = e.ContextFacts(D("0"), frozenset({"TechMart India"}), True, 0)
    assert e.evaluate(AGENT, POLICY, prop("1000"), dup).decision == "BLOCKED"
    assert e.evaluate(AGENT, None, prop("1000"), CTX).decision == "BLOCKED"  # fail closed
    foreign = e.AgentFacts(True, False, "active", D("75000"), "INR", ("electronics",))
    assert e.evaluate(foreign, POLICY, prop("1000"), CTX).decision == "BLOCKED"


def test_risk_thresholds():
    assert e.evaluate(AGENT, POLICY, prop("1000"), e.ContextFacts(D(0), frozenset({"TechMart India"}), False, 60)).decision == "REVIEW"
    assert e.evaluate(AGENT, POLICY, prop("1000"), e.ContextFacts(D(0), frozenset({"TechMart India"}), False, 90)).decision == "BLOCKED"


def test_engine_has_no_trust_score_input():
    """HARD RULE: trust can never override limits. Enforced structurally: no trust field/parameter exists in engine inputs."""
    import dataclasses
    names = set(inspect.signature(e.evaluate).parameters)
    for cls in (e.AgentFacts, e.PolicyFacts, e.ProposalFacts, e.ContextFacts):
        names |= {f.name for f in dataclasses.fields(cls)}
    assert not [n for n in names if "trust" in n.lower()]


def test_explanations_list_rules():
    ev = e.evaluate(AGENT, POLICY, prop("30000"), CTX)
    assert {"agent_active", "budget_remaining", "approval_threshold"} <= {c.rule for c in ev.checks}
    assert "approval_threshold" in ev.summary


def test_state_machine_rejects_invalid_transitions(client):
    from app.database.session import SessionLocal
    from app.models import PurchaseProposal
    assert S.CAPTURED not in ALLOWED[S.PROPOSED]
    assert ALLOWED[S.CAPTURED] == set()
    p = PurchaseProposal(state="PROPOSED")
    import pytest
    with SessionLocal() as db:
        with pytest.raises(InvalidTransition):
            transition(db, p, S.CAPTURED, actor="t")
        p.state = "EVALUATED"
        with pytest.raises(InvalidTransition):  # auto-authorize needs explicit permission
            transition(db, p, S.AUTHORIZED, actor="t")
