from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from database.models import FeeType

Row = dict[str, Any]


class IntegrationError(Exception):
    pass


class FormatError(Exception):
    pass


@dataclass(frozen=True)
class SkippedRow:
    section: str
    transaction_id: str | None
    reason: str
    attributes: dict[str, str]


@dataclass(frozen=True)
class AssetIdentity:
    symbol: str
    currency: str
    exch_codes: frozenset[str] = frozenset()
    isin: str | None = None


@dataclass
class MappingResult:
    account_names: dict[str, str] = field(default_factory=dict)
    assets: dict[str, Row] = field(default_factory=dict)
    identities: dict[str, AssetIdentity] = field(default_factory=dict)
    accounts: dict[str, Row] = field(default_factory=dict)
    cash: dict[str, Row] = field(default_factory=dict)
    trade_orders: dict[str, Row] = field(default_factory=dict)
    trades: dict[str, Row] = field(default_factory=dict)
    trade_fees: dict[tuple[str, FeeType], Row] = field(default_factory=dict)
    fx_pairs: dict[str, Row] = field(default_factory=dict)
    fx_orders: dict[str, Row] = field(default_factory=dict)
    fx: dict[str, Row] = field(default_factory=dict)
    fx_fees: dict[tuple[str, FeeType], Row] = field(default_factory=dict)
    skipped: list[SkippedRow] = field(default_factory=list)

    def drop_asset(self, broker_asset_id: str, reason: str) -> None:
        self.assets.pop(broker_asset_id, None)
        self.identities.pop(broker_asset_id, None)
        order_ids = {
            order_id
            for order_id, order in self.trade_orders.items()
            if order["from_broker_asset_id"] == broker_asset_id
        }
        trade_ids = [
            trade_id
            for trade_id, trade in self.trades.items()
            if trade["from_trade_order_id"] in order_ids
        ]
        for trade_id in trade_ids:
            del self.trades[trade_id]
            self.skipped.append(
                SkippedRow(
                    "Trades", trade_id, reason, {"broker_asset_id": broker_asset_id}
                )
            )
        for order_id in order_ids:
            del self.trade_orders[order_id]
        for key in [key for key in self.trade_fees if key[0] in trade_ids]:
            del self.trade_fees[key]


class BrokerAdapter(Protocol):
    broker_id: str
    broker_name: str
    timezone: ZoneInfo

    def fetch(self, start: date, end: date) -> list[bytes]: ...

    def map(self, documents: Iterable[bytes]) -> MappingResult: ...
