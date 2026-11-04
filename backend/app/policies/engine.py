"""DETERMINISTIC financial policy engine.

Pure Python, no LLM, no I/O. Inputs are plain dataclasses so it is trivially testable.
Deliberately takes NO trust-score input: a high trust score can never loosen a rule.
Precedence: BLOCKED > REVIEW > REQUIRES_APPROVAL > APPROVED.
"""
from dataclasses import dataclass, field, asdict
from decimal import Decimal


@dataclass(frozen=True)
class AgentFacts:
    exists: bool
    owned_by_user: bool
    status: str  # active|inactive|revoked
    max_transaction: Decimal
    currency: str
    allowed_categories: tuple[str, ...]


@dataclass(frozen=True)
class PolicyFacts:
    is_active: bool
    currency: str
    max_budget: Decimal
    approval_threshold: Decimal
    approved_merchants_only: bool
    duplicate_purchase_check: bool
    auto_approve_enabled: bool = True
    risk_review_threshold: int = 60
    risk_block_threshold: int = 90


@dataclass(frozen=True)
class ProposalFacts:
    amount: Decimal
    currency: str
    merchant: str
    category: str
    product_id: str
    state: str = "PROPOSED"


@dataclass(frozen=True)
class ContextFacts:
    committed_spend: Decimal  # captured/authorized/order-created spend in policy currency
    approved_merchants: frozenset[str]
    duplicate_exists: bool
    risk_score: int = 0


@dataclass
class RuleResult:
    rule: str
    passed: bool
    severity: str  # BLOCK | REVIEW | APPROVAL | INFO
    detail: str


@dataclass
class Evaluation:
    decision: str
    checks: list[RuleResult] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {"decision": self.decision, "summary": self.summary, "checks": [asdict(c) for c in self.checks]}

    def failed(self, severity: str | None = None) -> list[RuleResult]:
        return [c for c in self.checks if not c.passed and (severity is None or c.severity == severity)]


EVALUABLE_STATES = {"PROPOSED", "EVALUATED", "PENDING_APPROVAL", "AUTHORIZED", "PAYPAL_ORDER_CREATED"}


def _norm(s: str) -> str:
    return s.strip().lower()


def evaluate(agent: AgentFacts, policy: PolicyFacts | None, proposal: ProposalFacts, ctx: ContextFacts) -> Evaluation:
    c: list[RuleResult] = []

    def add(rule: str, passed: bool, severity: str, ok: str, bad: str) -> None:
        c.append(RuleResult(rule, passed, severity, ok if passed else bad))

    # 1-3 agent identity / status / scope
    add("agent_identity", agent.exists and agent.owned_by_user, "BLOCK",
        "Agent exists and belongs to this user.", "Agent is unknown or not owned by this user.")
    add("agent_active", agent.status == "active", "BLOCK",
        "Agent is active.", f"Agent status is '{agent.status}', not active.")
    add("agent_currency_scope", _norm(agent.currency) == _norm(proposal.currency), "BLOCK",
        f"Agent currency {agent.currency} matches proposal.", f"Agent currency {agent.currency} != proposal currency {proposal.currency}.")
    # 4 category
    allowed = {_norm(x) for x in agent.allowed_categories}
    add("category_permission", _norm(proposal.category) in allowed, "BLOCK",
        f"Category '{proposal.category}' is permitted for this agent.",
        f"Category '{proposal.category}' is outside this agent's permitted categories.")
    # 5 max transaction
    add("max_transaction", proposal.amount <= agent.max_transaction, "BLOCK",
        f"Amount {proposal.amount} <= agent max transaction {agent.max_transaction}.",
        f"Amount {proposal.amount} exceeds agent max transaction {agent.max_transaction}.")
    # 11 policy validity
    policy_ok = policy is not None and policy.is_active
    add("policy_valid", policy_ok, "BLOCK", "An active policy applies.", "No active policy; refusing to spend (fail closed).")
    # 12 state validity
    add("state_valid", proposal.state in EVALUABLE_STATES, "BLOCK",
        f"Proposal state {proposal.state} is evaluable.", f"Proposal state {proposal.state} cannot be evaluated/executed.")

    if policy_ok:
        assert policy is not None
        add("policy_currency", _norm(policy.currency) == _norm(proposal.currency), "BLOCK",
            "Policy currency matches proposal.", f"Policy currency {policy.currency} != proposal currency {proposal.currency}.")
        # 6 budget
        remaining = policy.max_budget - ctx.committed_spend
        add("budget_remaining", proposal.amount <= remaining, "BLOCK",
            f"Amount {proposal.amount} fits remaining budget {remaining}.",
            f"Amount {proposal.amount} exceeds remaining budget {remaining} (max budget {policy.max_budget}).")
        # 8 duplicates
        if policy.duplicate_purchase_check:
            add("duplicate_purchase", not ctx.duplicate_exists, "BLOCK",
                "No duplicate purchase of this product.", "This product was already purchased or is already in flight.")
        # 7 merchant allowlist
        if policy.approved_merchants_only:
            listed = _norm(proposal.merchant) in {_norm(m) for m in ctx.approved_merchants}
            add("merchant_allowlist", listed, "REVIEW",
                f"Merchant '{proposal.merchant}' is on the allowlist.", f"Merchant '{proposal.merchant}' is not on the approved list.")
        # 10 risk signals
        add("risk_block", ctx.risk_score < policy.risk_block_threshold, "BLOCK",
            f"Risk score {ctx.risk_score} below block threshold {policy.risk_block_threshold}.",
            f"Risk score {ctx.risk_score} >= block threshold {policy.risk_block_threshold}.")
        add("risk_review", ctx.risk_score < policy.risk_review_threshold, "REVIEW",
            f"Risk score {ctx.risk_score} below review threshold {policy.risk_review_threshold}.",
            f"Risk score {ctx.risk_score} >= review threshold {policy.risk_review_threshold}.")
        # 9 approval threshold
        add("approval_threshold", proposal.amount <= policy.approval_threshold, "APPROVAL",
            f"Amount {proposal.amount} <= approval threshold {policy.approval_threshold}.",
            f"Amount {proposal.amount} > approval threshold {policy.approval_threshold}: human approval required.")

    if any(not r.passed and r.severity == "BLOCK" for r in c):
        decision = "BLOCKED"
    elif any(not r.passed and r.severity == "REVIEW" for r in c):
        decision = "REVIEW"
    elif any(not r.passed and r.severity == "APPROVAL" for r in c):
        decision = "REQUIRES_APPROVAL"
    else:
        decision = "APPROVED"
    failed = [r.rule for r in c if not r.passed]
    summary = f"{decision}: all {len(c)} checks passed." if not failed else f"{decision}: failed checks -> {', '.join(failed)}."
    return Evaluation(decision=decision, checks=c, summary=summary)


def hard_blocks(ev: Evaluation) -> list[RuleResult]:
    """Rules that must hold again at approval/payment time (revalidation)."""
    return ev.failed("BLOCK")
