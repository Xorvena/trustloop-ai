from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.serializers import approval_out
from app.approvals import service as svc
from app.core.security import current_user, rate_limit
from app.database.session import get_db
from app.models import User
from app.schemas.schemas import ApprovalDecisionIn, ApprovalOut
from app.services import proposals as proposal_svc

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("/pending", response_model=list[ApprovalOut])
def pending(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [approval_out(db, a) for a in svc.pending(db, user.id)]


@router.post("/{approval_id}/decision", response_model=ApprovalOut, dependencies=[Depends(rate_limit("decision", 30))])
def decide(approval_id: str, body: ApprovalDecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    def revalidate(db_, p):
        return proposal_svc.revalidation_failures(db_, p)
    return approval_out(db, svc.decide(db, user.id, approval_id, body.decision, revalidate))
