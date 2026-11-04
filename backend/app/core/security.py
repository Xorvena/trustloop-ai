import time
from collections import defaultdict, deque

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.models import User, utcnow

_bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode()[:72], hashed.encode())


def _secret() -> str:
    s = get_settings()
    if not s.jwt_secret or len(s.jwt_secret) < 16:
        raise HTTPException(503, "JWT_SECRET is not configured (min 16 chars).")
    return s.jwt_secret


def create_token(user_id: str) -> str:
    s = get_settings()
    exp = int(time.time()) + s.jwt_expire_minutes * 60
    return jwt.encode({"sub": user_id, "exp": exp}, _secret(), algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    if not cred:
        raise HTTPException(401, "Not authenticated.")
    try:
        sub = jwt.decode(cred.credentials, _secret(), algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token.")
    user = db.get(User, sub)
    if not user:
        raise HTTPException(401, "Unknown user.")
    return user


# --- in-memory sliding-window rate limiter (single process; use Redis for multi-instance production) ---
_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(name: str, limit: int, per_seconds: int = 60):
    def dep(request: Request):
        if not get_settings().rate_limit_enabled:
            return
        key = f"{name}:{request.client.host if request.client else 'unknown'}"
        now = time.time()
        q = _hits[key]
        while q and q[0] < now - per_seconds:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Too many requests. Please slow down.")
        q.append(now)
    return dep


def reset_rate_limits() -> None:
    _hits.clear()
