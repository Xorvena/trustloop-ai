"""Payment execution. Only this module (never the LLM) can create or capture PayPal orders."""
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.approvals import service as approvals
from app.audit import service as audit
from app.core.config import get_settings
from app.core.errors import ServiceError
from app.models import (Approval, ApprovalStatus, PaymentOrder, ProposalState as S, PurchaseProposal, Transaction,
                        WebhookEvent, utcnow)
from app.payments import paypal
from app.services import proposals as proposal_svc
from app.services import state_machine as sm
from app.services import trust

Q = Decimal("0.01")


def charge_amount(amount: Decimal, currency: str) -> tuple[Decimal, str]:
    """Convert the authoritative DB amount into the PayPal settlement currency (server-side only)."""
    s = get_settings()
    if currency == s.paypal_currency:
        return amount.quantize(Q), currency
    if currency == "INR":
        return (amount / s.inr_per_unit_paypal_currency).quantize(Q, ROUND_HALF_UP), s.paypal_currency
    raise ServiceError(422, "unsupported_currency", f"No conversion from {currency} to {s.paypal_currency} configured.")


def _own_proposal(db: Session, user_id: str, proposal_id: str) -> PurchaseProposal:
    p = db.get(PurchaseProposal, proposal_id)
    if not p or p.user_id != user_id:
        raise ServiceError(404, "proposal_not_found", "Proposal not found.")
    return p


def authorization_for(db: Session, p: PurchaseProposal) -> Approval:
    a = db.scalars(select(Approval).where(Approval.proposal_id == p.id, Approval.status == ApprovalStatus.APPROVED.value)
                   .order_by(Approval.created_at.desc())).first()
    if not a:
        raise ServiceError(403, "no_authorization", "No valid authorization record for this proposal.")
    return a


def revalidate_for_execution(db: Session, p: PurchaseProposal) -> Approval:
    """Server-side gate before ANY money operation: state, authorization, expiry, binding, hard policy rules."""
    if p.state not in (S.AUTHORIZED.value, S.PAYPAL_ORDER_CREATED.value):
        raise ServiceError(409, "invalid_state", f"Proposal is {p.state}; payment is not permitted.")
    a = authorization_for(db, p)
    if approvals.is_expired(a):
        po = db.scalars(select(PaymentOrder).where(PaymentOrder.proposal_id == p.id)).first()
        if po and po.status in ("CREATED", "CAPTURING"):
            po.status = "FAILED"
        sm.transition(db, p, S.EXPIRED, actor="system", reason="authorization expired before payment")
        audit.record(db, action="payment.rejected_expired", actor="system", user_id=p.user_id, proposal_id=p.id, details={"approval_id": a.id})
        db.commit()
        raise ServiceError(409, "approval_expired", "Authorization expired before payment; a new proposal is required.")
    if not approvals.binding_ok(a, p):
        approvals.invalidate_open(db, p, "binding mismatch at payment time", "system")
        db.commit()
        raise ServiceError(409, "approval_invalidated", "Transaction details changed after approval; approval is invalid.")
    failures = proposal_svc.revalidation_failures(db, p)
    if failures:
        sm.transition(db, p, S.BLOCKED, actor="system", reason="revalidation failed before payment")
        audit.record(db, action="payment.rejected_revalidation", actor="system", user_id=p.user_id, proposal_id=p.id, details={"failures": failures})
        db.commit()
        raise ServiceError(409, "revalidation_failed", "Policy revalidation failed; payment blocked.", {"failures": failures})
    return a


def create_order(db: Session, user_id: str, proposal_id: str) -> dict:
    p = _own_proposal(db, user_id, proposal_id)
    existing = db.scalars(select(PaymentOrder).where(PaymentOrder.proposal_id == p.id)).first()
    if existing and p.state == S.PAYPAL_ORDER_CREATED.value and existing.status == "CREATED":
        revalidate_for_execution(db, p)
        return _order_view(existing)  # idempotent
    a = revalidate_for_execution(db, p)
    if existing:
        raise ServiceError(409, "order_exists", "A payment order already exists for this proposal.")
    amount, cur = charge_amount(p.amount, p.currency)  # authoritative amount from DB, never from the browser
    client = paypal.get_client()
    try:
        order = client.create_order(reference_id=p.id, amount=amount, currency=cur, description=p.product_name,
                                    request_id=f"trustloop-order-{p.id}")
    except paypal.PayPalError as exc:
        audit.record(db, action="payment.order_failed", actor="paypal", user_id=user_id, proposal_id=p.id,
                     details={"status": exc.status, "issues": exc.issues})
        db.commit()
        raise ServiceError(502, "paypal_error", "PayPal rejected the order request.", {"issues": exc.issues}) from exc
    po = PaymentOrder(proposal_id=p.id, user_id=user_id, paypal_order_id=order["id"], charge_amount=amount, charge_currency=cur)
    db.add(po)
    a.consumed_at = utcnow()
    sm.transition(db, p, S.PAYPAL_ORDER_CREATED, actor="payments", reason="PayPal order created")
    audit.record(db, action="payment.order_created", actor="payments", user_id=user_id, proposal_id=p.id,
                 details={"paypal_order_id": order["id"], "charge_amount": str(amount), "charge_currency": cur})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        po = db.scalars(select(PaymentOrder).where(PaymentOrder.proposal_id == p.id)).one()
    return _order_view(po)


def _order_view(po: PaymentOrder) -> dict:
    return {"paypal_order_id": po.paypal_order_id, "proposal_id": po.proposal_id, "charge_amount": str(po.charge_amount),
            "charge_currency": po.charge_currency, "status": po.status}


def _receipt_view(t: Transaction, already: bool) -> dict:
    return {"transaction_id": t.id, "proposal_id": t.proposal_id, "paypal_order_id": t.paypal_order_id,
            "paypal_capture_id": t.paypal_capture_id, "amount": str(t.amount), "currency": t.currency,
            "charge_amount": str(t.charge_amount), "charge_currency": t.charge_currency, "payment_status": t.payment_status,
            "already_captured": already}


def capture(db: Session, user_id: str, paypal_order_id: str) -> dict:
    po = db.scalars(select(PaymentOrder).where(PaymentOrder.paypal_order_id == paypal_order_id, PaymentOrder.user_id == user_id)).first()
    if not po:
        raise ServiceError(404, "order_not_found", "Payment order not found.")
    p = db.get(PurchaseProposal, po.proposal_id)
    done = db.scalars(select(Transaction).where(Transaction.proposal_id == p.id)).first()
    if done:  # duplicate capture request: no second PayPal call
        return _receipt_view(done, True)
    revalidate_for_execution(db, p)
    claim = db.execute(update(PaymentOrder).where(PaymentOrder.id == po.id, PaymentOrder.status == "CREATED").values(status="CAPTURING"))
    db.commit()
    if claim.rowcount != 1:
        done = db.scalars(select(Transaction).where(Transaction.proposal_id == p.id)).first()
        if done:
            return _receipt_view(done, True)
        raise ServiceError(409, "capture_in_progress", "A capture for this order is already in progress.")
    client = paypal.get_client()
    try:
        res = client.capture_order(paypal_order_id, request_id=f"trustloop-capture-{paypal_order_id}")
    except paypal.PayPalError as exc:
        declined = "INSTRUMENT_DECLINED" in exc.issues
        po = db.get(PaymentOrder, po.id)
        po.status = "CREATED" if declined else "FAILED"  # declined instrument: buyer may retry with another funding source
        if not declined:
            sm.transition(db, p, S.FAILED, actor="payments", reason=f"capture failed (HTTP {exc.status})")
        audit.record(db, action="payment.capture_failed", actor="paypal", user_id=user_id, proposal_id=p.id,
                     details={"status": exc.status, "issues": exc.issues})
        trust.snapshot(db, p.agent, f"capture failed for {p.id[:8]}")
        db.commit()
        raise ServiceError(402 if declined else 502, "capture_failed", "PayPal could not capture this payment.", {"issues": exc.issues}) from exc
    return _finalize(db, p, po, res, actor="payments")


def _verify_capture(po: PaymentOrder, p: PurchaseProposal, res: dict) -> dict:
    """Authoritative verification of PayPal's response against OUR records."""
    try:
        unit = res["purchase_units"][0]
        cap = unit["payments"]["captures"][0]
        ok = (res.get("id") == po.paypal_order_id and res.get("status") == "COMPLETED" and cap.get("status") == "COMPLETED"
              and unit.get("reference_id") == p.id and Decimal(cap["amount"]["value"]) == po.charge_amount
              and cap["amount"]["currency_code"] == po.charge_currency)
    except (KeyError, IndexError, ArithmeticError, TypeError):
        ok, cap = False, {}
    return {"ok": ok, "capture": cap}


def _finalize(db: Session, p: PurchaseProposal, po: PaymentOrder, res: dict, actor: str) -> dict:
    v = _verify_capture(po, p, res)
    if not v["ok"]:
        po.status = "FAILED"
        sm.transition(db, p, S.FAILED, actor=actor, reason="PayPal response failed verification")
        audit.record(db, action="payment.verification_failed", actor=actor, user_id=p.user_id, proposal_id=p.id,
                     details={"paypal_order_id": po.paypal_order_id, "note": "Manual reconciliation required in PayPal dashboard."})
        db.commit()
        raise ServiceError(502, "verification_failed", "Payment response did not match our records; flagged for reconciliation.")
    cap = v["capture"]
    t = Transaction(proposal_id=p.id, user_id=p.user_id, paypal_order_id=po.paypal_order_id, paypal_capture_id=cap["id"],
                    amount=p.amount, currency=p.currency, charge_amount=po.charge_amount, charge_currency=po.charge_currency,
                    payment_status="COMPLETED", receipt={"paypal_status": res.get("status"), "create_time": cap.get("create_time")})
    db.add(t)
    po.status = "COMPLETED"
    sm.transition(db, p, S.CAPTURED, actor=actor, reason="verified PayPal capture")
    audit.record(db, action="payment.captured", actor=actor, user_id=p.user_id, proposal_id=p.id,
                 details={"capture_id": cap["id"], "amount": str(po.charge_amount), "currency": po.charge_currency})
    trust.snapshot(db, p.agent, f"payment captured for {p.id[:8]}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        t = db.scalars(select(Transaction).where(Transaction.proposal_id == p.id)).one()
        return _receipt_view(t, True)
    return _receipt_view(t, False)


def handle_webhook(db: Session, headers: dict, event: dict) -> dict:
    if not paypal.get_client().verify_webhook(headers, event):
        audit.record(db, action="webhook.rejected", actor="paypal_webhook", details={"reason": "signature verification failed"})
        db.commit()
        raise ServiceError(400, "invalid_signature", "Webhook signature verification failed.")
    eid, etype = event.get("id", ""), event.get("event_type", "")
    try:
        db.add(WebhookEvent(id=eid, event_type=etype))
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate_ignored"}
    res = event.get("resource", {})
    order_id = (res.get("supplementary_data", {}).get("related_ids", {}) or {}).get("order_id")
    audit.record(db, action="webhook.received", actor="paypal_webhook", details={"event_id": eid, "event_type": etype, "order_id": order_id})
    if etype == "PAYMENT.CAPTURE.COMPLETED" and order_id:
        po = db.scalars(select(PaymentOrder).where(PaymentOrder.paypal_order_id == order_id)).first()
        if po and not db.scalars(select(Transaction).where(Transaction.proposal_id == po.proposal_id)).first():
            p = db.get(PurchaseProposal, po.proposal_id)
            if p.state == S.PAYPAL_ORDER_CREATED.value:
                synthetic = {"id": order_id, "status": "COMPLETED", "purchase_units": [{"reference_id": p.id, "payments": {"captures": [res]}}]}
                _finalize(db, p, po, synthetic, actor="paypal_webhook")
                return {"status": "reconciled"}
    elif etype in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED") and res.get("id"):
        t = db.scalars(select(Transaction).where(Transaction.paypal_capture_id == res["id"])).first()
        if t:
            t.payment_status = etype.rsplit(".", 1)[1]
            audit.record(db, action="transaction.payment_status_changed", actor="paypal_webhook", user_id=t.user_id,
                         proposal_id=t.proposal_id, details={"event_id": eid, "payment_status": t.payment_status})
    db.commit()
    return {"status": "processed"}
