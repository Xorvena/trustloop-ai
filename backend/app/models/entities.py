"""SQLAlchemy models. Money is Numeric(14,2) / Decimal everywhere, with explicit currency."""
import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (JSON, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
                        UniqueConstraint, event)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


def UtcDateTime() -> DateTime:
    """DateTime(timezone=True); SQLite drops tzinfo so readers must use `as_utc`."""
    return DateTime(timezone=True)


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class ProposalState(str, enum.Enum):
    PROPOSED = "PROPOSED"
    EVALUATED = "EVALUATED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    AUTHORIZED = "AUTHORIZED"
    PAYPAL_ORDER_CREATED = "PAYPAL_ORDER_CREATED"
    CAPTURED = "CAPTURED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Decision(str, enum.Enum):
    APPROVED = "APPROVED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("agent_code", name="uq_agents_agent_code"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agent_code: Mapped[str] = mapped_column(String(40))  # the public internal ID, e.g. agent_001
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|inactive|revoked
    max_transaction: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    allowed_categories: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="My policy")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    max_budget: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    approval_threshold: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    approved_merchants_only: Mapped[bool] = mapped_column(Boolean, default=True)
    duplicate_purchase_check: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_approve_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_ttl_minutes: Mapped[int] = mapped_column(Integer, default=30)
    risk_review_threshold: Mapped[int] = mapped_column(Integer, default=60)
    risk_block_threshold: Mapped[int] = mapped_column(Integer, default=90)
    frequency_limit: Mapped[int] = mapped_column(Integer, default=5)
    frequency_window_minutes: Mapped[int] = mapped_column(Integer, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)


class ApprovedMerchant(Base):
    __tablename__ = "approved_merchants"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_merchant_per_user"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class Product(Base):
    """Curated static catalog. NOT live retailer data; availability is not verified."""
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    sku: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    merchant: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    description: Mapped[str] = mapped_column(Text, default="")
    specs: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(40), default="curated_static_catalog")


class PurchaseProposal(Base):
    __tablename__ = "purchase_proposals"
    __table_args__ = (Index("ix_proposal_user_state", "user_id", "state"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    policy_id: Mapped[str | None] = mapped_column(ForeignKey("policies.id"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(200))
    merchant: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    request_text: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(24), default=ProposalState.PROPOSED.value, index=True)
    decision: Mapped[str | None] = mapped_column(String(24), nullable=True)
    decision_explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic concurrency
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)
    __mapper_args__ = {"version_id_col": version}

    agent: Mapped[Agent] = relationship(lazy="joined")
    risk: Mapped["RiskAssessment | None"] = relationship(back_populates="proposal", uselist=False, lazy="joined")


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("purchase_proposals.id"), unique=True, index=True)
    score: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(12))
    signals: Mapped[list] = mapped_column(JSON, default=list)  # deterministic
    ai_signals: Mapped[list] = mapped_column(JSON, default=list)  # advisory (Gemini)
    ai_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    proposal: Mapped[PurchaseProposal] = relationship(back_populates="risk")


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("purchase_proposals.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[str] = mapped_column(String(32))
    product_id: Mapped[str] = mapped_column(String(32))
    merchant: Mapped[str] = mapped_column(String(160))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    reason: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(24), default="REQUIRES_APPROVAL")
    status: Mapped[str] = mapped_column(String(16), default=ApprovalStatus.PENDING.value, index=True)
    binding_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime())
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    proposal: Mapped[PurchaseProposal] = relationship(lazy="joined")


class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("purchase_proposals.id"), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    paypal_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    charge_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))  # in paypal currency
    charge_currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), default="CREATED")  # CREATED|CAPTURING|COMPLETED|FAILED
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("purchase_proposals.id"), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    paypal_order_id: Mapped[str] = mapped_column(String(64))
    paypal_capture_id: Mapped[str] = mapped_column(String(64), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    charge_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    charge_currency: Mapped[str] = mapped_column(String(3))
    payment_status: Mapped[str] = mapped_column(String(24))  # COMPLETED|REFUNDED|DENIED...
    receipt: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # PayPal event id => dedupe
    event_type: Mapped[str] = mapped_column(String(80))
    received_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class TrustSnapshot(Base):
    __tablename__ = "trust_snapshots"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    components: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class AuditLog(Base):
    """Append-only at the application layer (ORM hooks below). Not cryptographically tamper-proof."""
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80), index=True)
    proposal_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


@event.listens_for(AuditLog, "before_update")
def _audit_no_update(*_):
    raise PermissionError("audit_logs is append-only")


@event.listens_for(AuditLog, "before_delete")
def _audit_no_delete(*_):
    raise PermissionError("audit_logs is append-only")
