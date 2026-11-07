from app.models import Agent, Approval, Policy, Product, PurchaseProposal
from app.schemas.schemas import AgentOut, ApprovalOut, PolicyOut, ProposalOut, RiskOut
from app.services import trust


def agent_out(db, a: Agent, with_trust: bool = True) -> AgentOut:
    score = trust.compute(db, a)["score"] if with_trust else None
    return AgentOut(id=a.id, agent_id=a.agent_code, agent_name=a.name, description=a.description, status=a.status,
                    max_transaction=a.max_transaction, currency=a.currency, allowed_categories=list(a.allowed_categories or []),
                    trust_score=score, created_at=a.created_at)


def policy_out(p: Policy, merchants: list[str]) -> PolicyOut:
    out = PolicyOut.model_validate(p)
    out.approved_merchants = merchants
    return out


def proposal_out(p: PurchaseProposal) -> ProposalOut:
    return ProposalOut(id=p.id, agent_id=p.agent.agent_code, agent_name=p.agent.name, product_id=p.product_id,
                       product_name=p.product_name, merchant=p.merchant, category=p.category, amount=p.amount, currency=p.currency,
                       state=p.state, decision=p.decision, decision_explanation=p.decision_explanation or {},
                       risk=RiskOut.model_validate(p.risk) if p.risk else None, request_text=p.request_text,
                       rationale=p.rationale, created_at=p.created_at)


def approval_out(db, a: Approval) -> ApprovalOut:
    p = a.proposal
    product = db.get(Product, a.product_id)
    return ApprovalOut(id=a.id, proposal_id=a.proposal_id, status=a.status, kind=a.kind, reason=a.reason, amount=a.amount,
                       currency=a.currency, merchant=a.merchant, product_name=p.product_name, product_id=a.product_id,
                       image_url=product.image_url if product else None, image_source=product.image_source if product else None,
                       agent_id=p.agent.agent_code, agent_name=p.agent.name, agent_trust_score=trust.compute(db, p.agent)["score"],
                       policy_evaluation=p.decision_explanation or {}, risk=RiskOut.model_validate(p.risk) if p.risk else None,
                       expires_at=a.expires_at, created_at=a.created_at)
