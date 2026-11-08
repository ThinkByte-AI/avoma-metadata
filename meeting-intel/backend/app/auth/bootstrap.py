import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models import User

log = logging.getLogger("app.auth")


def ensure_bootstrap_admin(db: Session, email: str, password: str) -> bool:
    """Create the first admin if the users table is empty. Returns True if one was created."""
    if db.scalar(select(func.count()).select_from(User)):
        return False
    db.add(
        User(
            email=email.strip().lower(),
            name="Administrator",
            password_hash=hash_password(password),
            role="admin",
            access_scope="all",
            can_download=True,
        )
    )
    db.commit()
    log.info("bootstrap admin created", extra={"email": email.strip().lower()})
    return True
