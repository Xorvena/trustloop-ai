from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.serializers import proposal_out
from app.audit import service as audit_svc
from app.approvals import service as approvals
from app.core.security import current_user
from app.database.session import get_db
from app.models import Agent, Approval, AuditLog, PaymentOrder, ProposalState as S, PurchaseProposal, Transaction, User
from app.services import trust

router = APIRouter(prefix="/api", tags=["reporting"])


def _tx_row(p: PurchaseProposal, t: Transaction | None) -> dict:
    return {"id": p.id, "transaction_id": t.id if t else None, "product_name": p.product_name, "merchant": p.merchant,
            "amount": str(p.amount), "currency": p.currency, "agent_id": p.agent.agent_code, "agent_name": p.agent.name,
            "decision": p.decision, "state": p.state, "payment_status": t.payment_status if t else None,
            "risk_level": p.risk.level if p.risk else None, "created_at": p.created_at}


@router.get("/transactions")
def list_transactions(q: str | None = None, state: str | None = None, decision: str | None = None, agent_id: str | None = None,
                      sort: str = "created_at", order: str = "desc", limit: int = 100, offset: int = 0,
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    approvals.expire_stale(db, user.id)
    db.commit()
    stmt = select(PurchaseProposal, Transaction).outerjoin(Transaction, Transaction.proposal_id == PurchaseProposal.id) \
        .join(Agent, Agent.id == PurchaseProposal.agent_id).where(PurchaseProposal.user_id == user.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(PurchaseProposal.product_name).like(like), func.lower(PurchaseProposal.merchant).like(like),
                              PurchaseProposal.id.like(f"{q}%")))
    if state: stmt = stmt.where(PurchaseProposal.state == state)
    if decision: stmt = stmt.where(PurchaseProposal.decision == decision)
    if agent_id: stmt = stmt.where(Agent.agent_code == agent_id)
    col = {"created_at": PurchaseProposal.created_at, "amount": PurchaseProposal.amount, "merchant": PurchaseProposal.merchant,
           "product": PurchaseProposal.product_name}.get(sort, PurchaseProposal.created_at)
    stmt = stmt.order_by(col.asc() if order == "asc" else col.desc()).limit(min(limit, 500)).offset(max(offset, 0))
    return [_tx_row(p, t) for p, t in db.execute(stmt).unique()]


@router.get("/transactions/{pid}")
def get_transaction(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(PurchaseProposal, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Transaction not found.")
    t = db.scalars(select(Transaction).where(Transaction.proposal_id == p.id)).first()
    po = db.scalars(select(PaymentOrder).where(PaymentOrder.proposal_id == p.id)).first()
    aps = db.scalars(select(Approval).where(Approval.proposal_id == p.id).order_by(Approval.created_at)).all()
    logs = db.scalars(select(AuditLog).where(AuditLog.proposal_id == p.id).order_by(AuditLog.timestamp)).all()
    return {**_tx_row(p, t), "proposal": proposal_out(p).model_dump(mode="json"),
            "receipt": None if not t else {"paypal_order_id": t.paypal_order_id, "paypal_capture_id": t.paypal_capture_id,
                                           "charged": f"{t.charge_amount} {t.charge_currency}", "payment_status": t.payment_status, **(t.receipt or {})},
            "payment_order": None if not po else {"paypal_order_id": po.paypal_order_id, "status": po.status,
                                                  "charge_amount": str(po.charge_amount), "charge_currency": po.charge_currency},
            "approvals": [{"id": a.id, "status": a.status, "kind": a.kind, "expires_at": a.expires_at, "decided_at": a.decided_at} for a in aps],
            "audit": [{"id": l.id, "timestamp": l.timestamp, "actor": l.actor, "action": l.action, "details": l.details} for l in logs]}


@router.get("/analytics/overview")
def overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    approvals.expire_stale(db, user.id)
    db.commit()
    props = list(db.scalars(select(PurchaseProposal).where(PurchaseProposal.user_id == user.id).order_by(PurchaseProposal.created_at.desc())).unique())
    txs = {t.proposal_id: t for t in db.scalars(select(Transaction).where(Transaction.user_id == user.id))}
    spend: dict[str, Decimal] = defaultdict(Decimal)
    for t in txs.values():
        spend[t.currency] += t.amount
    agents = list(db.scalars(select(Agent).where(Agent.user_id == user.id)))
    alerts = []
    for p in props:
        if p.risk and (p.risk.level in ("high", "critical") or any(s["code"] == "prompt_injection" for s in p.risk.signals)):
            alerts.append({"proposal_id": p.id, "agent_id": p.agent.agent_code, "product_name": p.product_name, "level": p.risk.level,
                           "score": p.risk.score, "signals": [s["code"] for s in p.risk.signals], "created_at": p.created_at})
    timeline = db.scalars(select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.timestamp.desc()).limit(15)).all()
    return {
        "is_demo_data": False, "total_spending": dict(map(lambda kv: (kv[0], str(kv[1])), spend.items())),
        "approved_transactions": sum(1 for p in props if p.state in (S.AUTHORIZED.value, S.PAYPAL_ORDER_CREATED.value, S.CAPTURED.value)),
        "captured_transactions": len(txs),
        "blocked_transactions": sum(1 for p in props if p.state == S.BLOCKED.value),
        "pending_approvals": sum(1 for p in props if p.state == S.PENDING_APPROVAL.value),
        "active_agents": sum(1 for a in agents if a.status == "active"), "total_agents": len(agents),
        "agent_trust": [{"agent_id": a.agent_code, "agent_name": a.name, "score": trust.compute(db, a)["score"]} for a in agents],
        "recent_transactions": [_tx_row(p, txs.get(p.id)) for p in props[:8]],
        "risk_alerts": alerts[:8],
        "activity": [{"id": l.id, "timestamp": l.timestamp, "actor": l.actor, "action": l.action, "proposal_id": l.proposal_id} for l in timeline],
    }


@router.get("/analytics/spending")
def spending(user: User = Depends(current_user), db: Session = Depends(get_db)):
    props = list(db.scalars(select(PurchaseProposal).where(PurchaseProposal.user_id == user.id)).unique())
    txs = list(db.scalars(select(Transaction).where(Transaction.user_id == user.id)))
    by_day: dict[str, dict] = defaultdict(lambda: {"date": "", "spend": 0.0, "approved": 0, "blocked": 0, "pending": 0, "closed": 0, "risk_avg": 0.0, "n": 0})
    for t in txs:
        d = t.created_at.date().isoformat()
        by_day[d]["date"] = d
        by_day[d]["spend"] += float(t.amount)
    for p in props:
        d = p.created_at.date().isoformat()
        r = by_day[d]
        r["date"] = d
        bucket = ("approved" if p.state in ("AUTHORIZED", "PAYPAL_ORDER_CREATED", "CAPTURED")
                  else "blocked" if p.state == "BLOCKED"
                  else "pending" if p.state == "PENDING_APPROVAL" else "closed")   # closed = rejected / expired / cancelled / failed
        r[bucket] += 1
        if p.risk:
            r["risk_avg"] += p.risk.score
            r["n"] += 1
    series = []
    for d in sorted(by_day):
        r = by_day[d]
        r["risk_avg"] = round(r["risk_avg"] / r["n"], 1) if r["n"] else 0
        series.append(r)
    decisions = defaultdict(int)
    for p in props:
        decisions[p.decision or "UNEVALUATED"] += 1
    return {"daily": series, "decisions": dict(decisions)}


@router.get("/analytics/agents")
def agent_analytics(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = []
    for a in db.scalars(select(Agent).where(Agent.user_id == user.id)):
        props = list(db.scalars(select(PurchaseProposal).where(PurchaseProposal.agent_id == a.id)).unique())
        spent = sum((t.amount for t in db.scalars(select(Transaction).join(PurchaseProposal, PurchaseProposal.id == Transaction.proposal_id)
                                                  .where(PurchaseProposal.agent_id == a.id))), Decimal(0))
        out.append({"agent_id": a.agent_code, "agent_name": a.name, "status": a.status, "spend": str(spent), "currency": a.currency,
                    "proposals": len(props), "blocked": sum(p.state == "BLOCKED" for p in props),
                    "approved": sum(p.state in ("AUTHORIZED", "PAYPAL_ORDER_CREATED", "CAPTURED") for p in props),
                    "trust_score": trust.compute(db, a)["score"]})
    return out


@router.get("/audit-logs")
def audit_logs(proposal_id: str | None = None, action: str | None = None, limit: int = 100, offset: int = 0,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(AuditLog).where(AuditLog.user_id == user.id)
    if proposal_id: stmt = stmt.where(AuditLog.proposal_id == proposal_id)
    if action: stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    rows = db.scalars(stmt.order_by(AuditLog.timestamp.desc()).limit(min(limit, 500)).offset(max(offset, 0))).all()
    return [{"id": l.id, "timestamp": l.timestamp, "actor": l.actor, "action": l.action, "proposal_id": l.proposal_id, "details": l.details} for l in rows]
