from sqlalchemy.orm import Session

from app.models import AuditLog


def write_audit(
    db: Session,
    user_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict | None = None,
    ip: str | None = None,
) -> None:
    """Add an audit row to the current transaction (the caller commits)."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
            ip=ip,
        )
    )
