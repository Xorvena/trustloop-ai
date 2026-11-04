from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import shopping
from app.api.serializers import proposal_out
from app.core.security import current_user, rate_limit
from app.database.session import get_db
from app.models import Product, PurchaseProposal, User
from app.schemas.schemas import (EvaluationCreate, ProductOut, ProductSearchIn, ProposalAmend, ProposalCreate, ProposalOut)
from app.services import proposals as svc
from app.core.errors import ServiceError

router = APIRouter(prefix="/api", tags=["shopping"])


@router.get("/products", response_model=list[ProductOut])
def list_products(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Product).order_by(Product.category, Product.price)).all()


@router.post("/products/search", dependencies=[Depends(rate_limit("search", 30))])
def search_products(body: ProductSearchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    res = shopping.search(db, body.query)
    return {
        "requirements": res["requirements"].model_dump(), "summary": res["summary"],
        "intent_source": res["intent_source"], "explanation_source": res["explanation_source"],
        "catalog_notice": "Curated demo catalog; prices and availability are not live retailer data.",
        "results": [{"product": ProductOut.model_validate(r["product"]).model_dump(mode="json"), "score": r["score"],
                     "meets_requirements": r["meets_requirements"], "unmet": r["unmet"],
                     "suspicious_description": bool(r["injection_flags"]), "injection_flags": r["injection_flags"]}
                    for r in res["ranked"]],
    }


def _own(db: Session, user: User, pid: str) -> PurchaseProposal:
    p = db.get(PurchaseProposal, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Proposal not found.")
    return p


@router.post("/proposals", response_model=ProposalOut, status_code=201, dependencies=[Depends(rate_limit("proposal", 30))])
def create_proposal(body: ProposalCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Amount/merchant are NOT accepted from the client: they are read from the catalog row.
    return proposal_out(svc.create_proposal(db, user_id=user.id, agent_code=body.agent_id, product_id=body.product_id,
                                            request_text=body.request_text, rationale=body.rationale))


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(state: str | None = None, limit: int = 100, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(PurchaseProposal).where(PurchaseProposal.user_id == user.id)
    if state:
        q = q.where(PurchaseProposal.state == state)
    return [proposal_out(p) for p in db.scalars(q.order_by(PurchaseProposal.created_at.desc()).limit(min(limit, 500))).unique()]


@router.get("/proposals/{pid}", response_model=ProposalOut)
def get_proposal(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return proposal_out(_own(db, user, pid))


@router.post("/proposals/{pid}/amend", response_model=ProposalOut)
def amend_proposal(pid: str, body: ProposalAmend, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Changes transaction details after approval was requested; previous approval becomes INVALIDATED."""
    return proposal_out(svc.amend(db, _own(db, user, pid), user_id=user.id, amount=body.amount, merchant=body.merchant))


@router.post("/evaluations")
def evaluate_now(body: EvaluationCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Non-persisting re-evaluation of a proposal against the CURRENT policy (what-if). Does not change state."""
    p = _own(db, user, body.proposal_id)
    ev, rr = svc.evaluate(db, p, persist_risk=False)
    db.rollback()
    return {"proposal_id": p.id, "persisted": False, "evaluation": ev.to_dict(),
            "risk": {"score": rr.score, "level": rr.level, "signals": rr.signals, "ai_signals": rr.ai_signals, "ai_used": rr.ai_used}}


@router.get("/evaluations/{pid}")
def get_evaluation(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _own(db, user, pid)
    return {"proposal_id": p.id, "state": p.state, "decision": p.decision, "evaluation": p.decision_explanation,
            "risk": None if not p.risk else {"score": p.risk.score, "level": p.risk.level, "signals": p.risk.signals,
                                              "ai_signals": p.risk.ai_signals, "ai_used": p.risk.ai_used}}
