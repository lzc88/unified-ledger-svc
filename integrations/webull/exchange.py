import logging
import threading

import yfinance as yf

from config.config import YAHOO_EXCHANGE_TO_EXCH_CODES

log = logging.getLogger(__name__)


class YahooExchangeLookup:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, frozenset[str]] = {}

    def __call__(self, symbol: str) -> frozenset[str]:
        with self._lock:
            cached = self._cache.get(symbol)
        if cached is not None:
            return cached

        exchange = self._primary_exchange(symbol)
        codes = YAHOO_EXCHANGE_TO_EXCH_CODES.get(exchange or "", frozenset())

        if not codes:
            log.warning("no primary US exchange for %s (Yahoo said %r)", symbol, exchange)
            return frozenset()

        with self._lock:
            self._cache[symbol] = codes
        return codes

    @staticmethod
    def _primary_exchange(symbol: str) -> str | None:
        yahoo_symbol = symbol.strip().replace(".", "-").replace("/", "-").replace(" ", "-")
        try:
            return yf.Ticker(yahoo_symbol).info.get("exchange")
        except Exception as exc:
            log.warning("Yahoo exchange lookup for %s failed: %s", symbol, exc)
            return None
