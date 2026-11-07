import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.serializers import agent_out
from app.audit import service as audit
from app.core.security import current_user
from app.database.session import get_db
from app.models import Agent, TrustSnapshot, User
from app.schemas.schemas import AgentCreate, AgentOut, AgentPatch
from app.services import trust

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _own(db: Session, user: User, ident: str) -> Agent:
    a = db.scalars(select(Agent).where(Agent.user_id == user.id, (Agent.id == ident) | (Agent.agent_code == ident))).first()
    if not a:
        raise HTTPException(404, "Agent not found.")
    return a


@router.post("", response_model=AgentOut, status_code=201)
def create_agent(body: AgentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    code = body.agent_id or f"agent_{secrets.token_hex(3)}"
    a = Agent(user_id=user.id, agent_code=code, name=body.agent_name, description=body.description,
              max_transaction=body.max_transaction, currency=body.currency.upper(),
              allowed_categories=[c.strip().lower() for c in body.allowed_categories])
    db.add(a)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "agent_id already exists.")
    audit.record(db, action="agent.created", actor=f"user:{user.id}", user_id=user.id,
                 details={"agent_id": code, "max_transaction": str(a.max_transaction), "categories": a.allowed_categories})
    trust.snapshot(db, a, "agent created (no history yet)")
    db.commit()
    return agent_out(db, a)


@router.get("", response_model=list[AgentOut])
def list_agents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [agent_out(db, a) for a in db.scalars(select(Agent).where(Agent.user_id == user.id).order_by(Agent.created_at))]


@router.get("/{ident}", response_model=AgentOut)
def get_agent(ident: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return agent_out(db, _own(db, user, ident))


@router.patch("/{ident}", response_model=AgentOut)
def patch_agent(ident: str, body: AgentPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _own(db, user, ident)
    before = {"status": a.status, "max_transaction": str(a.max_transaction), "categories": list(a.allowed_categories or [])}
    if a.status == "revoked" and body.status and body.status != "revoked":
        raise HTTPException(409, "A revoked agent cannot be reactivated; create a new agent.")
    if body.agent_name is not None: a.name = body.agent_name
    if body.description is not None: a.description = body.description
    if body.max_transaction is not None: a.max_transaction = body.max_transaction
    if body.allowed_categories is not None: a.allowed_categories = [c.strip().lower() for c in body.allowed_categories]
    if body.status is not None: a.status = body.status
    after = {"status": a.status, "max_transaction": str(a.max_transaction), "categories": list(a.allowed_categories or [])}
    audit.record(db, action="agent.permissions_changed", actor=f"user:{user.id}", user_id=user.id,
                 details={"agent_id": a.agent_code, "before": before, "after": after})
    db.commit()
    return agent_out(db, a)


@router.get("/{ident}/trust")
def agent_trust(ident: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _own(db, user, ident)
    hist = db.scalars(select(TrustSnapshot).where(TrustSnapshot.agent_id == a.id).order_by(TrustSnapshot.created_at)).all()
    return {"agent_id": a.agent_code, "agent_name": a.name, **trust.compute(db, a),
            "history": [{"score": h.score, "reason": h.reason, "created_at": h.created_at, "components": h.components} for h in hist]}
