"""Demo-grade auth: bcrypt password check + HS256 JWT (SPEC §8; residual risk in threat model).

Tokens carry only the user id; role and business are re-read from the DB on every request, so a
role change takes effect immediately.
"""

from datetime import datetime, timedelta
from functools import lru_cache

import bcrypt
import jwt

from app.db.models import User

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=8)


class InvalidToken(Exception):
    pass


def issue_token(user: User, secret: str, now: datetime) -> tuple[str, datetime]:
    expires = now + TOKEN_TTL
    token = jwt.encode({"sub": str(user.id), "iat": int(now.timestamp()), "exp": int(expires.timestamp())},
                       secret, algorithm=ALGORITHM)
    return token, expires


def read_token(token: str, secret: str) -> int:
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["sub", "exp", "iat"]})
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError) as e:
        raise InvalidToken(str(e)) from e


@lru_cache
def _dummy_hash() -> bytes:
    return bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())


def verify_password(user: User | None, password: str) -> bool:
    """Constant-ish time: unknown emails still pay for a bcrypt check (no user enumeration by timing)."""
    hashed = user.password_hash.encode() if user else _dummy_hash()
    ok = bcrypt.checkpw(password.encode(), hashed)
    return ok and user is not None
