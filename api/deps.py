from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session, sessionmaker

from auth.service import active_user
from auth.tokens import InvalidTokenError, decode_token
from config.config import AUTH_COOKIE_NAME
from database.db import SessionLocal
from database.models import User
from integrations.base import BrokerAdapter
from integrations.ibkr import IbkrAdapter
from integrations.openfigi import OpenFigiClient
from portfolio.market import MarketData, YahooMarketData

_market_data = YahooMarketData()
_ibkr = IbkrAdapter()
_session_cookie = APIKeyCookie(name=AUTH_COOKIE_NAME, auto_error=False)

SessionToken = Annotated[str | None, Depends(_session_cookie)]


def get_session_factory() -> sessionmaker[Session]:
    return SessionLocal


def get_ibkr_adapter() -> BrokerAdapter:
    return _ibkr


def get_openfigi_factory() -> Callable[[str | None], OpenFigiClient]:
    return OpenFigiClient


def get_market_data() -> MarketData:
    return _market_data


SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
FigiFactory = Annotated[
    Callable[[str | None], OpenFigiClient], Depends(get_openfigi_factory)
]
Market = Annotated[MarketData, Depends(get_market_data)]


def get_current_user(session_factory: SessionFactory, token: SessionToken) -> User:
    unauthenticated = HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    if token is None:
        raise unauthenticated

    try:
        claims = decode_token(token)
    except InvalidTokenError:
        raise unauthenticated from None

    with session_factory() as session:
        user = active_user(session, claims)

    if user is None:
        raise unauthenticated

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
