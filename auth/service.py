import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.config import AUTH_SESSION_TTL
from database.models import User, UserSession

from .passwords import hash_password, verify_password
from .tokens import TokenClaims

USER_NAME_CONSTRAINT = "uq_users_user_name"


class UsernameTakenError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def register_user(session: Session, username: str, password: str) -> User:
    user = User(
        user_id=str(uuid.uuid4()),
        user_name=username,
        password_hash=hash_password(password),
    )

    try:
        with session.begin_nested():
            session.add(user)
    except IntegrityError as exc:
        if getattr(exc.orig.diag, "constraint_name", None) == USER_NAME_CONSTRAINT:
            raise UsernameTakenError(f"username {username!r} is already taken") from None
        raise

    return user


def authenticate(session: Session, username: str, password: str) -> User | None:
    user = session.scalars(select(User).where(User.user_name == username)).one_or_none()
    password_hash = user.password_hash if user is not None else None

    if not verify_password(password, password_hash):
        return None

    return user


def start_session(session: Session, user_id: str) -> UserSession:
    user_session = UserSession(from_user_id=user_id, expires_at=_now() + AUTH_SESSION_TTL)
    session.add(user_session)
    session.flush()
    return user_session


def active_user(session: Session, claims: TokenClaims) -> User | None:
    statement = (
        select(User)
        .join(UserSession, UserSession.from_user_id == User.user_id)
        .where(
            UserSession.session_id == claims.session_id,
            UserSession.from_user_id == claims.user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > _now(),
        )
    )
    return session.scalars(statement).one_or_none()


def revoke_session(session: Session, claims: TokenClaims) -> None:
    session.execute(
        update(UserSession)
        .where(
            UserSession.session_id == claims.session_id,
            UserSession.from_user_id == claims.user_id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
