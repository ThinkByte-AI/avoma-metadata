from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.security import COOKIE_NAME, decode_token
from app.db import get_db
from app.errors import ApiError
from app.models import User


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise ApiError(401, "unauthenticated", "Please sign in.")
    user = db.get(User, decode_token(token))
    if user is None or not user.is_active:
        raise ApiError(401, "unauthenticated", "Please sign in.")
    request.state.user_id = user.id
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise ApiError(403, "forbidden", "Administrator access is required.")
    return user


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None
