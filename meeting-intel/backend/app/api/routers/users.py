from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import UserCreate, UserOut, UserUpdate
from app.audit import write_audit
from app.auth.deps import client_ip, require_admin
from app.auth.security import hash_password
from app.db import get_db
from app.errors import ApiError, not_found
from app.models import User

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> User:
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email)):
        raise ApiError(409, "email_taken", "A user with this email already exists.")
    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        role=body.role,
        access_scope=body.access_scope,
        account_label=body.account_label or None,
        can_download=body.can_download,
    )
    db.add(user)
    db.flush()
    write_audit(db, admin.id, "user.create", "user", str(user.id), {"email": user.email, "role": user.role},
                client_ip(request))
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("user")
    changes = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (changes.get("is_active") is False or changes.get("role", "admin") != "admin"):
        raise ApiError(400, "cannot_modify_self", "You can't deactivate or demote your own account.")
    password = changes.pop("password", None)
    for field, value in changes.items():
        setattr(user, field, value)
    if password:
        user.password_hash = hash_password(password)
    write_audit(
        db, admin.id, "user.update", "user", str(user.id),
        {"fields": sorted(changes) + (["password"] if password else [])}, client_ip(request),
    )
    db.commit()
    return user
