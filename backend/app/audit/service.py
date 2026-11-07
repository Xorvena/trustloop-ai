"""Append-only application audit log. Only `record` and read helpers exist; ORM hooks block UPDATE/DELETE."""
from sqlalchemy.orm import Session

from app.models import AuditLog


def record(db: Session, *, action: str, actor: str, user_id: str | None = None,
           proposal_id: str | None = None, details: dict | None = None) -> AuditLog:
    entry = AuditLog(action=action, actor=actor, user_id=user_id, proposal_id=proposal_id, details=details or {})
    db.add(entry)
    db.flush()
    return entry
