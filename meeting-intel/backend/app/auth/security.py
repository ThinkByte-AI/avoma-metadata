from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.config import get_settings
from app.errors import ApiError

_hasher = PasswordHash.recommended()  # argon2id
# Used to spend the same time verifying when the email is unknown (no user-enumeration by timing).
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

COOKIE_NAME = "mi_session"
_ALGO = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    try:
        return _hasher.verify(password, password_hash)
    except Exception:
        return False


def create_token(user_id: int) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=s.jwt_ttl_min)}
    return jwt.encode(payload, s.jwt_secret, algorithm=_ALGO)


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGO], options={"require": ["sub", "exp"]})
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise ApiError(401, "unauthenticated", "Your session has expired. Please sign in again.") from None
