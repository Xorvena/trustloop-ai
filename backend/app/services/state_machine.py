"""Controlled proposal/transaction state machine.

Happy path: PROPOSED -> EVALUATED -> PENDING_APPROVAL -> AUTHORIZED -> PAYPAL_ORDER_CREATED -> CAPTURED
EVALUATED -> AUTHORIZED is allowed ONLY when the caller states the policy permits auto-approval.
PENDING_APPROVAL/AUTHORIZED -> EVALUATED exists solely for amendments (details changed => re-evaluate).
Concurrency: PurchaseProposal uses SQLAlchemy version_id_col; a concurrent writer gets StaleDataError (-> HTTP 409).
"""
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.models import PurchaseProposal, ProposalState as S

TERMINAL = {S.CAPTURED, S.BLOCKED, S.REJECTED, S.EXPIRED, S.FAILED, S.CANCELLED}

ALLOWED: dict[S, set[S]] = {
    S.PROPOSED: {S.EVALUATED, S.BLOCKED, S.FAILED, S.CANCELLED},
    S.EVALUATED: {S.PENDING_APPROVAL, S.AUTHORIZED, S.BLOCKED, S.CANCELLED},
    S.PENDING_APPROVAL: {S.AUTHORIZED, S.REJECTED, S.EXPIRED, S.CANCELLED, S.BLOCKED, S.EVALUATED},
    S.AUTHORIZED: {S.PAYPAL_ORDER_CREATED, S.EXPIRED, S.CANCELLED, S.BLOCKED, S.EVALUATED},
    S.PAYPAL_ORDER_CREATED: {S.CAPTURED, S.FAILED, S.EXPIRED, S.CANCELLED},
    **{t: set() for t in TERMINAL},
}


class InvalidTransition(Exception):
    pass


def transition(db: Session, proposal: PurchaseProposal, new_state: S, *, actor: str,
               reason: str = "", auto_approve_permitted: bool = False) -> PurchaseProposal:
    current = S(proposal.state)
    if new_state not in ALLOWED[current]:
        raise InvalidTransition(f"{current.value} -> {new_state.value} is not allowed")
    if current == S.EVALUATED and new_state == S.AUTHORIZED and not auto_approve_permitted:
        raise InvalidTransition("EVALUATED -> AUTHORIZED requires an explicit auto-approve policy")
    proposal.state = new_state.value
    db.flush()  # raises StaleDataError if another writer changed the row concurrently
    audit.record(db, action="transaction.status_changed", actor=actor, user_id=proposal.user_id,
                 proposal_id=proposal.id, details={"from": current.value, "to": new_state.value, "reason": reason})
    return proposal
