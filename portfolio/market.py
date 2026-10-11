import logging
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

import yfinance as yf

log = logging.getLogger(__name__)

US_SUFFIX = ""
EXCH_CODE_SUFFIXES = {
    "US": US_SUFFIX,
    "UW": US_SUFFIX,
    "UQ": US_SUFFIX,
    "UR": US_SUFFIX,
    "UN": US_SUFFIX,
    "UP": US_SUFFIX,
    "UA": US_SUFFIX,
    "UF": US_SUFFIX,
    "LN": ".L",
    "GY": ".DE",
    "GF": ".F",
    "NA": ".AS",
    "FP": ".PA",
    "SE": ".SW",
    "IM": ".MI",
    "HK": ".HK",
    "SP": ".SI",
    "AT": ".AX",
    "CT": ".TO",
    "JT": ".T",
}
CACHE_TTL_SECONDS = 300


class MarketDataError(Exception):
    pass


@dataclass(frozen=True)
class Quote:
    price: Decimal
    currency: str


def yahoo_symbol(ticker: str, exch_code: str) -> str | None:
    suffix = EXCH_CODE_SUFFIXES.get(exch_code)
    if suffix is None:
        return None
    symbol = ticker.strip().replace("/", "-").replace(" ", "-")
    if exch_code == "HK" and symbol.isdigit():
        symbol = symbol.zfill(4)
    return symbol + suffix


def fx_symbol(currency: str, base: str) -> str:
    return f"{currency}{base}=X"


class MarketData(Protocol):
    def quotes(self, symbols: set[str]) -> dict[str, Quote]: ...

    def monthly_closes(
        self, symbols: set[str], start: date
    ) -> dict[str, dict[date, Decimal]]: ...


class YahooMarketData:
    def __init__(self, ttl: float = CACHE_TTL_SECONDS) -> None:
        self._ttl = ttl
        self._lock = threading.Lock()
        self._cache: dict[tuple, tuple[float, object]] = {}

    def quotes(self, symbols: set[str]) -> dict[str, Quote]:
        quotes = {}
        for symbol in sorted(symbols):
            try:
                quotes[symbol] = self._cached(
                    ("quote", symbol), lambda s=symbol: self._quote(s)
                )
            except MarketDataError:
                pass
        return quotes

    def monthly_closes(
        self, symbols: set[str], start: date
    ) -> dict[str, dict[date, Decimal]]:
        key = ("monthly", tuple(sorted(symbols)), start)
        return self._cached(key, lambda: self._monthly(sorted(symbols), start))

    def _cached(self, key: tuple, load: Callable):
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < self._ttl:
                return hit[1]
        value = load()
        with self._lock:
            self._cache[key] = (time.monotonic(), value)
        return value

    @staticmethod
    def _quote(symbol: str) -> Quote:
        try:
            info = yf.Ticker(symbol).fast_info
            price, currency = info.last_price, info.currency
        except Exception as exc:
            log.warning("Yahoo quote for %s failed: %s", symbol, exc)
            raise MarketDataError(f"no quote from Yahoo for {symbol}") from exc
        if price is None or math.isnan(price) or not currency:
            raise MarketDataError(f"no quote from Yahoo for {symbol}")
        return Quote(Decimal(str(price)), currency)

    @staticmethod
    def _monthly(symbols: list[str], start: date) -> dict[str, dict[date, Decimal]]:
        if not symbols:
            return {}
        try:
            history = yf.download(
                symbols,
                start=start.isoformat(),
                interval="1mo",
                auto_adjust=False,
                progress=False,
                multi_level_index=True,
            )
        except Exception as exc:
            log.warning("Yahoo history download failed: %s", exc)
            raise MarketDataError("no price history from Yahoo") from exc
        if history is None or history.empty:
            raise MarketDataError("no price history from Yahoo")
        closes = history["Close"].ffill()
        return {
            symbol: {
                ts.date().replace(day=1): Decimal(str(value))
                for ts, value in closes[symbol].items()
                if not math.isnan(value)
            }
            for symbol in symbols
            if symbol in closes
        }
