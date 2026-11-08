from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import LoginIn, UserOut
from app.audit import write_audit
from app.auth.deps import client_ip, current_user
from app.auth.security import COOKIE_NAME, create_token, verify_password
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import User
from app.ratelimit import login_limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    email = body.email.strip().lower()
    if not login_limiter.hit(f"{email}|{client_ip(request)}"):
        raise ApiError(429, "rate_limited", "Too many sign-in attempts. Please wait a minute and try again.")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    ok = verify_password(body.password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        write_audit(db, None, "auth.login_failed", "user", None, {"email": email}, client_ip(request))
        db.commit()
        raise ApiError(401, "invalid_credentials", "Incorrect email or password.")

    user.last_login_at = datetime.now(UTC)
    write_audit(db, user.id, "auth.login", "user", str(user.id), None, client_ip(request))
    db.commit()

    s = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        create_token(user.id),
        max_age=s.jwt_ttl_min * 60,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
