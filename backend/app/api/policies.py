from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import gemini
from app.api.serializers import policy_out
from app.audit import service as audit
from app.core.security import current_user, rate_limit
from app.database.session import get_db
from app.models import ApprovedMerchant, Policy, User
from app.policies.parser import parse_policy
from app.schemas.schemas import PolicyCreate, PolicyOut, PolicyParseIn, PolicyPatch

router = APIRouter(prefix="/api", tags=["policies"])


def _merchants(db: Session, user_id: str) -> list[str]:
    return [m for (m,) in db.execute(select(ApprovedMerchant.name).where(ApprovedMerchant.user_id == user_id).order_by(ApprovedMerchant.name))]


def _set_merchants(db: Session, user_id: str, names: list[str]) -> None:
    wanted = {n.strip() for n in names if n.strip()}
    for m in db.scalars(select(ApprovedMerchant).where(ApprovedMerchant.user_id == user_id)):
        if m.name not in wanted:
            db.delete(m)
        else:
            wanted.discard(m.name)
    for n in sorted(wanted):
        db.add(ApprovedMerchant(user_id=user_id, name=n[:160]))
    db.flush()


def _own(db: Session, user: User, pid: str) -> Policy:
    p = db.get(Policy, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Policy not found.")
    return p


@router.post("/policies/parse", dependencies=[Depends(rate_limit("parse", 20))])
def parse(body: PolicyParseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Returns a DRAFT only. Nothing is stored and no existing policy is touched; the user must confirm via POST /api/policies."""
    try:
        draft = parse_policy(body.text)
    except gemini.GeminiUnavailable as e:
        raise HTTPException(503, str(e))
    except (gemini.GeminiBadOutput, ValueError) as e:
        raise HTTPException(422, f"Could not interpret policy safely: {e}")
    audit.record(db, action="policy.parsed", actor=f"user:{user.id}", user_id=user.id, details={"source": draft.source})
    db.commit()
    return {"draft": draft.model_dump(mode="json"), "requires_confirmation": True,
            "note": "Draft only. Review and confirm to save; AI output is never applied automatically."}


@router.post("/policies", response_model=PolicyOut, status_code=201)
def create_policy(body: PolicyCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for old in db.scalars(select(Policy).where(Policy.user_id == user.id, Policy.is_active.is_(True))):
        old.is_active = False  # one active policy per user
    data = body.model_dump(exclude={"approved_merchants"})
    p = Policy(user_id=user.id, **data)
    db.add(p)
    db.flush()
    if body.approved_merchants is not None:
        _set_merchants(db, user.id, body.approved_merchants)
    audit.record(db, action="policy.created", actor=f"user:{user.id}", user_id=user.id,
                 details={"policy_id": p.id, "max_budget": str(p.max_budget), "approval_threshold": str(p.approval_threshold)})
    db.commit()
    return policy_out(p, _merchants(db, user.id))


@router.get("/policies", response_model=list[PolicyOut])
def list_policies(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ms = _merchants(db, user.id)
    return [policy_out(p, ms) for p in db.scalars(select(Policy).where(Policy.user_id == user.id).order_by(Policy.created_at.desc()))]


@router.get("/policies/{pid}", response_model=PolicyOut)
def get_policy(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return policy_out(_own(db, user, pid), _merchants(db, user.id))


@router.patch("/policies/{pid}", response_model=PolicyOut)
def patch_policy(pid: str, body: PolicyPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _own(db, user, pid)
    changes = body.model_dump(exclude_unset=True, exclude={"approved_merchants"})
    before = {k: str(getattr(p, k)) for k in changes}
    for k, v in changes.items():
        setattr(p, k, v)
    if p.approval_threshold > p.max_budget:
        db.rollback()
        raise HTTPException(422, "approval_threshold cannot exceed max_budget.")
    if changes.get("is_active"):
        for other in db.scalars(select(Policy).where(Policy.user_id == user.id, Policy.id != p.id, Policy.is_active.is_(True))):
            other.is_active = False
    if body.approved_merchants is not None:
        _set_merchants(db, user.id, body.approved_merchants)
    audit.record(db, action="policy.modified", actor=f"user:{user.id}", user_id=user.id,
                 details={"policy_id": p.id, "before": before, "after": {k: str(v) for k, v in changes.items()},
                          "merchants_replaced": body.approved_merchants is not None})
    db.commit()
    return policy_out(p, _merchants(db, user.id))


@router.get("/merchants")
def list_merchants(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"approved_merchants": _merchants(db, user.id)}
