"""Small in-process sliding-window rate limiter (per user). Enough for a single API instance."""
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends

from app.auth.deps import current_user
from app.errors import ApiError
from app.models import User

AI_LIMIT_PER_MIN = 20
LOGIN_LIMIT_PER_MIN = 10  # per email + client address


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_sec: float = 60.0):
        self.limit, self.window = limit, window_sec
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


ai_limiter = SlidingWindowLimiter(AI_LIMIT_PER_MIN)
login_limiter = SlidingWindowLimiter(LOGIN_LIMIT_PER_MIN)


def ai_rate_limit(user: User = Depends(current_user)) -> User:
    if not ai_limiter.hit(f"user:{user.id}"):
        raise ApiError(429, "rate_limited", "Too many questions in a minute. Please wait a moment and try again.")
    return user
