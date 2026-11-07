from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


class UserOut(ORM):
    id: str
    email: str
    name: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class AgentCreate(BaseModel):
    agent_name: str = Field(min_length=1, max_length=120)
    agent_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_\-]{3,40}$")
    description: str = Field(default="", max_length=1000)
    max_transaction: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    allowed_categories: list[str] = Field(default_factory=list, max_length=20)


class AgentPatch(BaseModel):
    agent_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    max_transaction: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    allowed_categories: list[str] | None = Field(default=None, max_length=20)
    status: Literal["active", "inactive", "revoked"] | None = None


class AgentOut(BaseModel):
    id: str
    agent_id: str
    agent_name: str
    description: str
    status: str
    max_transaction: Decimal
    currency: str
    allowed_categories: list[str]
    trust_score: int | None = None
    created_at: datetime


class PolicyCreate(BaseModel):
    name: str = Field(default="My policy", max_length=120)
    raw_text: str = Field(default="", max_length=4000)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    max_budget: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    approval_threshold: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    approved_merchants_only: bool = True
    duplicate_purchase_check: bool = True
    auto_approve_enabled: bool = True
    approval_ttl_minutes: int = Field(default=30, ge=1, le=1440)
    risk_review_threshold: int = Field(default=60, ge=1, le=100)
    risk_block_threshold: int = Field(default=90, ge=1, le=100)
    frequency_limit: int = Field(default=5, ge=1, le=1000)
    frequency_window_minutes: int = Field(default=60, ge=1, le=1440)
    approved_merchants: list[str] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _check(self):
        if self.approval_threshold > self.max_budget:
            raise ValueError("approval_threshold cannot exceed max_budget")
        if self.risk_review_threshold > self.risk_block_threshold:
            raise ValueError("risk_review_threshold cannot exceed risk_block_threshold")
        return self

    @field_validator("currency")
    @classmethod
    def _cur(cls, v):
        return v.upper()


class PolicyPatch(BaseModel):
    name: str | None = None
    max_budget: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    approval_threshold: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    approved_merchants_only: bool | None = None
    duplicate_purchase_check: bool | None = None
    auto_approve_enabled: bool | None = None
    approval_ttl_minutes: int | None = Field(default=None, ge=1, le=1440)
    is_active: bool | None = None
    approved_merchants: list[str] | None = Field(default=None, max_length=50)


class PolicyParseIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)


class PolicyOut(ORM):
    id: str
    name: str
    raw_text: str
    currency: str
    max_budget: Decimal
    approval_threshold: Decimal
    approved_merchants_only: bool
    duplicate_purchase_check: bool
    auto_approve_enabled: bool
    approval_ttl_minutes: int
    risk_review_threshold: int
    risk_block_threshold: int
    frequency_limit: int
    frequency_window_minutes: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    approved_merchants: list[str] = []


class ProductOut(ORM):
    id: str
    sku: str
    name: str
    brand: str = ""
    model: str = ""
    merchant: str
    category: str
    product_type: str = ""
    price: Decimal
    currency: str
    description: str
    specs: dict
    availability: str = "in_stock"
    image_url: str | None = None
    image_source: str | None = None  # "illustration" (generic, not a photo) | "licensed_photo" | None
    source: str


class ProductSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=2000)


class ProposalCreate(BaseModel):
    agent_id: str = Field(pattern=r"^[A-Za-z0-9_\-]{3,40}$")  # agent_code
    product_id: str = Field(min_length=1, max_length=32)
    request_text: str = Field(default="", max_length=2000)
    rationale: str = Field(default="", max_length=2000)


class ProposalAmend(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    merchant: str | None = Field(default=None, max_length=160)


class EvaluationCreate(BaseModel):
    proposal_id: str


class RiskOut(ORM):
    score: int
    level: str
    signals: list
    ai_signals: list
    ai_used: bool


class ProposalOut(BaseModel):
    id: str
    agent_id: str  # public agent code
    agent_name: str
    product_id: str
    product_name: str
    merchant: str
    category: str
    amount: Decimal
    currency: str
    state: str
    decision: str | None
    decision_explanation: dict
    risk: RiskOut | None
    request_text: str
    rationale: str
    created_at: datetime


class ApprovalOut(BaseModel):
    id: str
    proposal_id: str
    status: str
    kind: str
    reason: str
    amount: Decimal
    currency: str
    merchant: str
    product_name: str
    product_id: str
    image_url: str | None = None
    image_source: str | None = None
    agent_id: str
    agent_name: str
    agent_trust_score: int | None
    policy_evaluation: dict
    risk: RiskOut | None
    expires_at: datetime
    created_at: datetime


class ApprovalDecisionIn(BaseModel):
    decision: Literal["approve", "reject"]


class CreateOrderIn(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=32)  # NOTE: no amount field: amount comes from the DB


class CaptureIn(BaseModel):
    paypal_order_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9\-_]+$")
