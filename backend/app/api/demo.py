"""Optional demo bootstrap: creates a policy, merchants and agents for the signed-in user. Clearly labelled [DEMO]."""
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.catalog import APPROVED_DEMO_MERCHANTS
from app.audit import service as audit
from app.core.security import current_user
from app.database.session import get_db
from app.models import Agent, ApprovedMerchant, Policy, User
from app.services import trust

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/seed", status_code=201)
def seed(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.scalars(select(Agent).where(Agent.user_id == user.id)).first():
        return {"seeded": False, "detail": "You already have agents; demo seed skipped."}
    for m in APPROVED_DEMO_MERCHANTS:
        db.add(ApprovedMerchant(user_id=user.id, name=m))
    db.add(Policy(user_id=user.id, name="[DEMO] Budget ₹75,000 / approval above ₹25,000", currency="INR",
                  raw_text="Never spend above ₹75,000. Ask me before any purchase above ₹25,000. Only buy from approved merchants. Never purchase the same product twice.",
                  max_budget=Decimal("75000"), approval_threshold=Decimal("25000")))
    suffix = user.id[:4]
    specs = [(f"agent_001_{suffix}", "LaptopShoppingAgent", "[DEMO] Shops for electronics.", "75000", ["electronics"], "active"),
             (f"agent_002_{suffix}", "HomeOfficeAgent", "[DEMO] Furniture only.", "20000", ["furniture"], "active"),
             (f"agent_003_{suffix}", "DormantAgent", "[DEMO] Deactivated agent for the blocked-agent scenario.", "75000", ["electronics"], "inactive")]
    for code, name, desc, mx, cats, status in specs:
        a = Agent(user_id=user.id, agent_code=code, name=name, description=desc, max_transaction=Decimal(mx), allowed_categories=cats, status=status)
        db.add(a)
        db.flush()
        trust.snapshot(db, a, "agent created (no history yet)")
    audit.record(db, action="demo.seeded", actor=f"user:{user.id}", user_id=user.id, details={"note": "demo configuration created"})
    db.commit()
    return {"seeded": True, "agents": [s[0] for s in specs]}
