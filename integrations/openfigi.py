import logging
import re
import threading
import time
from collections.abc import Callable, Collection, Mapping
from typing import Any

import httpx

from config.config import get_openfigi_settings
from integrations.base import AssetIdentity, IntegrationError, MappingResult, Row

log = logging.getLogger(__name__)

MAPPING_URL = "https://api.openfigi.com/v3/mapping"
KEYLESS_BATCH_SIZE = 5
KEYED_BATCH_SIZE = 100
KEYLESS_REQUEST_INTERVAL = 60.0 / 25
KEYED_REQUEST_INTERVAL = 6.0 / 25
RATE_LIMIT_BACKOFF = 60.0
MAX_ATTEMPTS = 3
FIGI_PATTERN = re.compile(r"^BBG[0-9A-Z]{9}$")


class OpenFigiError(IntegrationError):
    pass


class OpenFigiClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._headers = {"X-OPENFIGI-APIKEY": api_key} if api_key else {}
        self._batch_size = KEYED_BATCH_SIZE if api_key else KEYLESS_BATCH_SIZE
        self._interval = KEYED_REQUEST_INTERVAL if api_key else KEYLESS_REQUEST_INTERVAL
        self._http = http or httpx.Client(timeout=30.0)
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_request: float | None = None

    def trading_venue_listings(
        self, identities: Mapping[str, AssetIdentity]
    ) -> dict[str, Row | None]:
        keys = list(identities)
        listings: dict[str, Row | None] = {}
        for i in range(0, len(keys), self._batch_size):
            batch = keys[i : i + self._batch_size]
            results = self._post([_job(identities[key]) for key in batch])
            for key, result in zip(batch, results, strict=True):
                listings[key] = _trading_venue_listing(key, identities[key], result)
        return listings

    def _post(self, jobs: list[dict[str, str]]) -> list[dict[str, Any]]:
        with self._lock:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                self._throttle()
                try:
                    response = self._http.post(
                        MAPPING_URL, json=jobs, headers=self._headers
                    )
                except httpx.HTTPError as exc:
                    raise OpenFigiError(
                        f"{type(exc).__name__} calling OpenFIGI"
                    ) from None
                if response.status_code == 429 and attempt < MAX_ATTEMPTS:
                    self._sleep(RATE_LIMIT_BACKOFF)
                    continue
                if response.status_code != 200:
                    raise OpenFigiError(f"HTTP {response.status_code} from OpenFIGI")
                try:
                    results = response.json()
                except ValueError:
                    raise OpenFigiError("OpenFIGI response is not JSON") from None
                if not isinstance(results, list) or len(results) != len(jobs):
                    raise OpenFigiError("OpenFIGI did not return one result per job")
                return results
        raise AssertionError("unreachable")

    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self._interval - (time.monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = time.monotonic()


def assign_figis(
    result: MappingResult, known: Collection[str], client: OpenFigiClient
) -> None:
    unknown = {
        broker_asset_id: identity
        for broker_asset_id, identity in result.identities.items()
        if broker_asset_id not in known and broker_asset_id in result.assets
    }
    for broker_asset_id, identity in list(unknown.items()):
        if not identity.exch_codes:
            del unknown[broker_asset_id]
            result.drop_asset(
                broker_asset_id, "listing exchange has no OpenFIGI exchange code"
            )
    if not unknown:
        return
    for broker_asset_id, listing in client.trading_venue_listings(unknown).items():
        if listing is None:
            result.drop_asset(
                broker_asset_id, "no unique trading-venue FIGI from OpenFIGI"
            )
        else:
            result.assets[broker_asset_id].update(listing)


def client_from_settings() -> OpenFigiClient:
    api_key = get_openfigi_settings().openfigi_api_key
    return OpenFigiClient(api_key.get_secret_value() if api_key else None)


def _job(identity: AssetIdentity) -> dict[str, str]:
    job = {"marketSecDes": "Equity", "currency": identity.currency}
    if identity.isin:
        job |= {"idType": "ID_ISIN", "idValue": identity.isin}
    else:
        job |= {"idType": "TICKER", "idValue": _bloomberg_ticker(identity.symbol)}
    return job


def _bloomberg_ticker(symbol: str) -> str:
    return re.sub(r"[ .\-]+", "/", symbol.strip())


def _trading_venue_listing(
    key: str, identity: AssetIdentity, result: dict[str, Any]
) -> Row | None:
    if "error" in result:
        log.warning("OpenFIGI could not map %s: %s", key, result["error"])
        return None
    listings = {
        item["figi"]: item
        for item in result.get("data") or []
        if item.get("exchCode") in identity.exch_codes
        and FIGI_PATTERN.match(item.get("figi") or "")
    }
    if len(listings) != 1:
        if listings:
            log.warning("OpenFIGI matched %s to several listings", key)
        return None
    figi, item = listings.popitem()
    if not item.get("ticker"):
        log.warning("OpenFIGI returned no ticker for %s", key)
        return None
    return {
        "trading_venue_figi": figi,
        "composite_figi": _figi_or_none(item.get("compositeFIGI")),
        "share_class_figi": _figi_or_none(item.get("shareClassFIGI")),
        "ticker": item["ticker"],
        "listing_exchange": item["exchCode"],
    }


def _figi_or_none(value: str | None) -> str | None:
    return value if value and FIGI_PATTERN.match(value) else None
