import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt

from config.config import AUTH_JWT_ALGORITHM, get_auth_settings


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    session_id: uuid.UUID


def _secret() -> str:
    return get_auth_settings().auth_jwt_secret.get_secret_value()


def encode_token(user_id: str, session_id: uuid.UUID, expires_at: datetime) -> str:
    claims = {
        "sub": user_id,
        "sid": str(session_id),
        "iat": datetime.now(timezone.utc),
        "exp": expires_at,
    }
    return jwt.encode(claims, _secret(), algorithm=AUTH_JWT_ALGORITHM)


def decode_token(token: str) -> TokenClaims:
    try:
        claims = jwt.decode(
            token,
            _secret(),
            algorithms=[AUTH_JWT_ALGORITHM],
            options={"require": ["sub", "sid", "exp", "iat"]},
        )
        return TokenClaims(user_id=claims["sub"], session_id=uuid.UUID(claims["sid"]))
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise InvalidTokenError("invalid session token") from exc
