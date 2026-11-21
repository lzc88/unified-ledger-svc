from fastapi import APIRouter, HTTPException, Response, status

from api.deps import CurrentUser, SessionFactory, SessionToken
from api.schemas.auth import Credentials, Me
from auth.service import (
    UsernameTakenError,
    authenticate,
    register_user,
    revoke_session,
    start_session,
)
from auth.tokens import InvalidTokenError, decode_token, encode_token
from config.config import AUTH_COOKIE_NAME, AUTH_SESSION_TTL, get_auth_settings
from database.models import User, UserSession

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: Credentials, session_factory: SessionFactory, response: Response) -> Me:
    try:
        with session_factory.begin() as session:
            user = register_user(session, body.username, body.password.get_secret_value())
            user_session = start_session(session, user.user_id)
    except UsernameTakenError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    _set_session_cookie(response, user_session)
    return _me(user)


@router.post("/login")
def login(body: Credentials, session_factory: SessionFactory, response: Response) -> Me:
    with session_factory.begin() as session:
        user = authenticate(session, body.username, body.password.get_secret_value())
        if user is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "invalid username or password"
            )

        user_session = start_session(session, user.user_id)

    _set_session_cookie(response, user_session)
    return _me(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session_factory: SessionFactory, token: SessionToken) -> Response:
    if token is not None:
        try:
            claims = decode_token(token)
        except InvalidTokenError:
            pass
        else:
            with session_factory.begin() as session:
                revoke_session(session, claims)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        AUTH_COOKIE_NAME,
        path="/",
        secure=get_auth_settings().auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/me")
def me(user: CurrentUser) -> Me:
    return _me(user)


def _me(user: User) -> Me:
    return Me(user_id=user.user_id, username=user.user_name)


def _set_session_cookie(response: Response, user_session: UserSession) -> None:
    token = encode_token(
        user_session.from_user_id, user_session.session_id, user_session.expires_at
    )
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=int(AUTH_SESSION_TTL.total_seconds()),
        path="/",
        secure=get_auth_settings().auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
