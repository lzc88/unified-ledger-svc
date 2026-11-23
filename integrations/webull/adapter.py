from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from config.config import (
    WEBULL_ACCESS_TOKEN_CREDENTIAL,
    WEBULL_APP_KEY_CREDENTIAL,
    WEBULL_APP_SECRET_CREDENTIAL,
    WEBULL_CREDENTIAL_KEYS,
    WEBULL_CURRENCY_TO_EXCH_CODES,
    WEBULL_INSTRUMENT_TYPE_TO_LISTING_CATEGORY,
    WEBULL_PRIMARY_EXCHANGE_LOOKUP_CURRENCIES,
    WEBULL_TOKEN_NORMAL,
)
from database.models import ListingCategory
from integrations.base import (
    AssetIdentity,
    FormatError,
    IntegrationError,
    SkippedRow,
    Snapshot,
)

from .client import WebullClient
from .exchange import YahooExchangeLookup

POSITIONS_SECTION = "Positions"
BALANCES_SECTION = "Balances"

ClientFactory = Callable[..., WebullClient]
ExchangeLookup = Callable[[str], frozenset[str]]


class TokenNotVerifiedError(IntegrationError):
    pass


class _Skip(Exception):
    pass


class WebullAdapter:
    broker_id = "WEBULL"
    broker_name = "Webull"
    timezone = ZoneInfo("Asia/Singapore")
    credential_keys = WEBULL_CREDENTIAL_KEYS

    def __init__(
        self,
        client_factory: ClientFactory = WebullClient,
        exchange_lookup: ExchangeLookup | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._exchange_lookup = exchange_lookup or YahooExchangeLookup()

    def exch_codes(self, symbol: str, currency: str) -> frozenset[str]:
        if currency in WEBULL_PRIMARY_EXCHANGE_LOOKUP_CURRENCIES:
            return self._exchange_lookup(symbol)
        return WEBULL_CURRENCY_TO_EXCH_CODES.get(currency, frozenset())

    def client(self, app_key: str, app_secret: str, token: str | None = None) -> WebullClient:
        return self._client_factory(app_key, app_secret, token)

    def fetch_snapshot(self, credentials: Mapping[str, str]) -> Snapshot:
        token = credentials[WEBULL_ACCESS_TOKEN_CREDENTIAL]
        client = self.client(
            credentials[WEBULL_APP_KEY_CREDENTIAL],
            credentials[WEBULL_APP_SECRET_CREDENTIAL],
            token,
        )

        status = client.check_token(token).status
        if status != WEBULL_TOKEN_NORMAL:
            raise TokenNotVerifiedError(
                f"Webull access token is {status}; "
                "re-verify the Webull connection under my investments"
            )

        snapshot = Snapshot()

        for account in client.accounts():
            account_id = _account_id(account)
            snapshot.accounts[account_id] = {"account_id": account_id}
            snapshot.account_names[account_id] = _account_name(account, account_id)

            _map_balance(snapshot, client.balance(account_id), account_id)

            for position in client.positions(account_id):
                try:
                    _map_position(snapshot, position, account_id, self.exch_codes)
                except _Skip as skip:
                    snapshot.skipped.append(
                        SkippedRow(
                            POSITIONS_SECTION,
                            _text(position, "instrument_id") or _text(position, "symbol"),
                            str(skip),
                            {key: str(value) for key, value in position.items()},
                        )
                    )

        return snapshot


def _account_id(account: Mapping[str, Any]) -> str:
    account_id = _text(account, "account_id")
    if account_id is None:
        raise FormatError("Webull account list row has no account_id")

    return account_id


def _account_name(account: Mapping[str, Any], account_id: str) -> str:
    return _text(account, "account_number") or account_id


def _map_balance(snapshot: Snapshot, balance: Mapping[str, Any], account_id: str) -> None:
    rows = balance.get("account_currency_assets")
    if not isinstance(rows, list):
        raise FormatError("Webull balance has no account_currency_assets")

    for row in rows:
        currency = _require(row, "currency", BALANCES_SECTION)
        amount = _decimal(row, "cash_balance", BALANCES_SECTION)

        if amount == 0:
            continue

        key = (account_id, currency)
        existing = snapshot.cash.get(key)

        snapshot.cash[key] = {
            "from_account_id": account_id,
            "currency": currency,
            "balance": amount + (existing["balance"] if existing else Decimal(0)),
        }


def _map_position(
    snapshot: Snapshot,
    row: Mapping[str, Any],
    account_id: str,
    exch_codes: Callable[[str, str], frozenset[str]],
) -> None:
    section = POSITIONS_SECTION

    instrument_type = _require(row, "instrument_type", section)
    category = WEBULL_INSTRUMENT_TYPE_TO_LISTING_CATEGORY.get(instrument_type)
    if category is None:
        raise _Skip(f"instrument type {instrument_type!r} is not tracked")

    quantity = _decimal(row, "quantity", section)
    if quantity == 0:
        raise _Skip("zero quantity")

    symbol = _require(row, "symbol", section)
    currency = _require(row, "currency", section)
    asset_id = _text(row, "instrument_id") or f"{symbol}:{currency}"

    if _text(row, "total_cost") is not None:
        cost_basis = _decimal(row, "total_cost", section)
    else:
        cost_basis = _decimal(row, "cost_price", section) * quantity

    snapshot.assets.setdefault(
        asset_id,
        {"listing_category": ListingCategory(category), "listing_currency": currency},
    )

    if asset_id not in snapshot.identities:
        snapshot.identities[asset_id] = AssetIdentity(
            symbol=symbol,
            currency=currency,
            exch_codes=exch_codes(symbol, currency),
        )

    key = (account_id, asset_id)
    existing = snapshot.positions.get(key)
    if existing is not None:
        quantity += existing["quantity"]
        cost_basis += existing["cost_basis"]

    if quantity == 0:
        snapshot.positions.pop(key, None)
        if not any(held == asset_id for _, held in snapshot.positions):
            snapshot.assets.pop(asset_id, None)
            snapshot.identities.pop(asset_id, None)
        return

    snapshot.positions[key] = {
        "from_account_id": account_id,
        "from_broker_asset_id": asset_id,
        "quantity": quantity,
        "cost_basis": cost_basis,
        "currency": currency,
    }


def _text(row: Mapping[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def _require(row: Mapping[str, Any], key: str, section: str) -> str:
    value = _text(row, key)
    if value is None:
        raise FormatError(f"Webull {section} row is missing {key}")

    return value


def _decimal(row: Mapping[str, Any], key: str, section: str) -> Decimal:
    value = _require(row, key, section)

    try:
        return Decimal(value)
    except InvalidOperation:
        raise FormatError(f"Webull {section} {key} is not a number: {value!r}") from None
