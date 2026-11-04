"""Human-in-the-loop approvals, bound to exact transaction details, with expiry and replay protection."""
import hashlib
import json
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import ServiceError
from app.models import Approval, ApprovalStatus, ProposalState as S, PurchaseProposal, as_utc, utcnow
from app.services import state_machine as sm


def binding_hash(p: PurchaseProposal, user_id: str, agent_id: str, expires_at: datetime) -> str:
    """Hash over every field the approval is bound to. Any change => hash mismatch => approval invalid."""
    payload = {"proposal_id": p.id, "user_id": user_id, "agent_id": agent_id, "amount": str(p.amount),
               "currency": p.currency, "merchant": p.merchant, "product_id": p.product_id,
               "expires_at": as_utc(expires_at).isoformat()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def create(db: Session, p: PurchaseProposal, *, kind: str, reason: str, ttl_minutes: int, actor: str) -> Approval:
    expires = utcnow() + timedelta(minutes=ttl_minutes)
    a = Approval(proposal_id=p.id, user_id=p.user_id, agent_id=p.agent_id, product_id=p.product_id, merchant=p.merchant,
                 amount=p.amount, currency=p.currency, reason=reason, kind=kind, expires_at=expires,
                 binding_hash=binding_hash(p, p.user_id, p.agent_id, expires))
    if kind == "AUTO_APPROVED":  # policy-authorized: still leaves an authorization record
        a.status, a.decided_at = ApprovalStatus.APPROVED.value, utcnow()
    db.add(a)
    db.flush()
    audit.record(db, action="approval.created", actor=actor, user_id=p.user_id, proposal_id=p.id,
                 details={"approval_id": a.id, "kind": kind, "expires_at": expires.isoformat()})
    return a


def is_expired(a: Approval) -> bool:
    return utcnow() >= as_utc(a.expires_at)


def binding_ok(a: Approval, p: PurchaseProposal) -> bool:
    return a.binding_hash == binding_hash(p, a.user_id, a.agent_id, a.expires_at) and \
        (a.amount, a.currency, a.merchant, a.product_id, a.agent_id) == (p.amount, p.currency, p.merchant, p.product_id, p.agent_id)


def invalidate_open(db: Session, p: PurchaseProposal, reason: str, actor: str) -> int:
    n = 0
    for a in db.scalars(select(Approval).where(Approval.proposal_id == p.id,
                        Approval.status.in_([ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value]))):
        a.status = ApprovalStatus.INVALIDATED.value
        n += 1
        audit.record(db, action="approval.invalidated", actor=actor, user_id=p.user_id, proposal_id=p.id,
                     details={"approval_id": a.id, "reason": reason})
    db.flush()
    return n


def expire_stale(db: Session, user_id: str) -> int:
    """Lazily expire pending approvals and their proposals."""
    n = 0
    for a in db.scalars(select(Approval).where(Approval.user_id == user_id, Approval.status == ApprovalStatus.PENDING.value)):
        if is_expired(a):
            a.status = ApprovalStatus.EXPIRED.value
            if a.proposal.state == S.PENDING_APPROVAL.value:
                sm.transition(db, a.proposal, S.EXPIRED, actor="system", reason="approval expired")
            audit.record(db, action="approval.expired", actor="system", user_id=user_id, proposal_id=a.proposal_id,
                         details={"approval_id": a.id})
            n += 1
    db.flush()
    return n


def pending(db: Session, user_id: str) -> list[Approval]:
    expire_stale(db, user_id)
    db.commit()
    return list(db.scalars(select(Approval).where(Approval.user_id == user_id, Approval.status == ApprovalStatus.PENDING.value)
                           .order_by(Approval.created_at.desc())))


def decide(db: Session, user_id: str, approval_id: str, decision: str, revalidate) -> Approval:
    """`revalidate(db, proposal)` returns a list of failed hard-rule details (re-run of the policy engine)."""
    a = db.get(Approval, approval_id)
    if not a or a.user_id != user_id:  # ownership: other users' approvals look nonexistent
        raise ServiceError(404, "approval_not_found", "Approval not found.")
    p = a.proposal
    actor = f"user:{user_id}"
    if a.status != ApprovalStatus.PENDING.value:  # replay protection
        raise ServiceError(409, "approval_already_decided", f"Approval is already {a.status}.")
    if is_expired(a):
        a.status = ApprovalStatus.EXPIRED.value
        if p.state == S.PENDING_APPROVAL.value:
            sm.transition(db, p, S.EXPIRED, actor="system", reason="approval expired before decision")
        audit.record(db, action="approval.expired", actor="system", user_id=user_id, proposal_id=p.id, details={"approval_id": a.id})
        db.commit()
        raise ServiceError(410, "approval_expired", "This approval request has expired.")
    if p.state != S.PENDING_APPROVAL.value:
        raise ServiceError(409, "invalid_state", f"Proposal is {p.state}, not pending approval.")
    if not binding_ok(a, p):
        a.status = ApprovalStatus.INVALIDATED.value
        audit.record(db, action="approval.invalidated", actor="system", user_id=user_id, proposal_id=p.id,
                     details={"approval_id": a.id, "reason": "transaction details changed since approval was requested"})
        db.commit()
        raise ServiceError(409, "approval_invalidated", "Transaction details changed; this approval is no longer valid.")
    if decision == "reject":
        a.status, a.decided_at = ApprovalStatus.REJECTED.value, utcnow()
        sm.transition(db, p, S.REJECTED, actor=actor, reason="rejected by user")
        audit.record(db, action="approval.rejected", actor=actor, user_id=user_id, proposal_id=p.id, details={"approval_id": a.id})
        db.commit()
        return a
    failures = revalidate(db, p)
    if failures:
        a.status = ApprovalStatus.INVALIDATED.value
        sm.transition(db, p, S.BLOCKED, actor="system", reason="revalidation failed at approval time")
        audit.record(db, action="approval.revalidation_failed", actor="system", user_id=user_id, proposal_id=p.id,
                     details={"approval_id": a.id, "failures": failures})
        db.commit()
        raise ServiceError(409, "revalidation_failed", "Policy revalidation failed; transaction blocked.", {"failures": failures})
    res = db.execute(update(Approval).where(Approval.id == a.id, Approval.status == ApprovalStatus.PENDING.value)
                     .values(status=ApprovalStatus.APPROVED.value, decided_at=utcnow()))
    if res.rowcount != 1:  # concurrent decision won the race
        db.rollback()
        raise ServiceError(409, "approval_already_decided", "Approval was decided concurrently.")
    db.refresh(a)
    sm.transition(db, p, S.AUTHORIZED, actor=actor, reason="approved by user")
    audit.record(db, action="approval.approved", actor=actor, user_id=user_id, proposal_id=p.id,
                 details={"approval_id": a.id, "amount": str(p.amount), "currency": p.currency})
    db.commit()
    return a
