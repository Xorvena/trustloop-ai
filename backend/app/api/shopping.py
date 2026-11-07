from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import shopping
from app.agents.catalog import CATEGORIES, TYPE_ATTRIBUTES
from app.providers.dummyjson import PROVIDER_TYPE_TO_CATEGORY
from app.api.serializers import proposal_out
from app.core.security import current_user, rate_limit
from app.database.session import get_db
from app.models import ApprovedMerchant, Product, PurchaseProposal, User
from app.schemas.schemas import (EvaluationCreate, ProductOut, ProductSearchIn, ProposalAmend, ProposalCreate, ProposalOut)
from app.services import proposals as svc
from app.core.errors import ServiceError

router = APIRouter(prefix="/api", tags=["shopping"])


@router.get("/products", response_model=list[ProductOut])
def list_products(category: str | None = None, product_type: str | None = None, brand: str | None = None,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Product)
    if category: q = q.where(Product.category == category)
    if product_type: q = q.where(Product.product_type == product_type)
    if brand: q = q.where(func.lower(Product.brand) == brand.lower())
    return db.scalars(q.order_by(Product.category, Product.product_type, Product.price)).all()


@router.get("/products/categories")
def categories(user: User = Depends(current_user)):
    """Categories (what agents are granted permission for) and their product types."""
    cats = {c: list(t) for c, t in CATEGORIES.items()}
    for ptype, cat in PROVIDER_TYPE_TO_CATEGORY.items():
        cats.setdefault(cat, [])
        if ptype not in cats[cat]:
            cats[cat].append(ptype)
    return {"categories": dict(sorted(cats.items())), "type_attributes": TYPE_ATTRIBUTES}


def _result_item(r: dict, approved: set[str]) -> dict:
    return {"product": ProductOut.model_validate(r["product"]).model_dump(mode="json"), "kind": r["kind"], "score": r["score"],
            "merchant_approved": r["product"].merchant.strip().lower() in approved, "unconfirmed_terms": r["unconfirmed_terms"],
            "meets_requirements": r["meets_requirements"], "checks": r["checks"], "unmet": r["unmet"], "relation": r["relation"],
            "suspicious_description": bool(r["injection_flags"]), "injection_flags": r["injection_flags"]}


@router.post("/products/search", dependencies=[Depends(rate_limit("search", 30))])
def search_products(body: ProductSearchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    res = shopping.search(db, body.query)
    approved = {m.strip().lower() for (m,) in db.execute(select(ApprovedMerchant.name).where(ApprovedMerchant.user_id == user.id))}
    items = [_result_item(r, approved) for r in res["matches"] + res["alternatives"]]
    sm = res["summary"]
    it = res["intent"]
    return {
        "status": res["status"],  # matches_found | no_exact_match | nothing_found
        "requirements": res["requirements"].model_dump(), "interpreted_as": res["interpreted_as"],
        "unverifiable_terms": res["unverifiable_terms"], "notes": res["notes"], "provider_status": res["provider_status"],
        "summary": sm["text"], "summary_source": sm["source"], "summary_model": sm["model"], "summary_used_fallback_model": sm["used_fallback_model"],
        "summary_fallback_reason": sm["fallback_reason"], "summary_fallback_message": sm["fallback_message"],
        "intent_source": it["source"], "intent_model": it["model"], "intent_used_fallback_model": it["used_fallback_model"], "intent_fallback_reason": it["fallback_reason"],
        "intent_fallback_message": it["fallback_message"], "intent_notes": it["notes"],
        "catalog_notice": "Demo data (built-in catalog + demo provider): prices, specs and availability are illustrative, not live retailer data.",
        "matches": [i for i in items if i["kind"] == "match"], "alternatives": [i for i in items if i["kind"] == "alternative"],
        "results": items,  # matches first, then alternatives (kept for backward compatibility)
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


@router.post("/proposals/{pid}/cancel", response_model=ProposalOut)
def cancel_proposal(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Cancel an UNPAID proposal (pending approval, authorized, or order created). Frees its budget; captured payments cannot be cancelled."""
    return proposal_out(svc.cancel(db, _own(db, user, pid), user_id=user.id))


@router.get("/budget")
def budget(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Budget used/remaining under the active policy, and the unpaid or paid proposals currently counted against it."""
    return svc.budget_status(db, user.id)


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
