from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from database.db import SessionLocal
from integrations.base import BrokerAdapter
from integrations.ibkr import IbkrAdapter
from integrations.openfigi import OpenFigiClient, client_from_settings
from portfolio.market import MarketData, YahooMarketData

_market_data = YahooMarketData()
_ibkr = IbkrAdapter()


def get_session_factory() -> sessionmaker[Session]:
    return SessionLocal


def get_ibkr_adapter() -> BrokerAdapter:
    return _ibkr


@lru_cache
def get_openfigi_client() -> OpenFigiClient:
    return client_from_settings()


def get_market_data() -> MarketData:
    return _market_data


SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
Figi = Annotated[OpenFigiClient, Depends(get_openfigi_client)]
Market = Annotated[MarketData, Depends(get_market_data)]
