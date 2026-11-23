from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from zoneinfo import ZoneInfo

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
class Snapshot:
    account_names: dict[str, str] = field(default_factory=dict)
    assets: dict[str, Row] = field(default_factory=dict)
    identities: dict[str, AssetIdentity] = field(default_factory=dict)
    accounts: dict[str, Row] = field(default_factory=dict)
    positions: dict[tuple[str, str], Row] = field(default_factory=dict)
    cash: dict[tuple[str, str], Row] = field(default_factory=dict)
    skipped: list[SkippedRow] = field(default_factory=list)

    def drop_asset(self, broker_asset_id: str, reason: str) -> None:
        self.assets.pop(broker_asset_id, None)
        self.identities.pop(broker_asset_id, None)

        keys = [key for key in self.positions if key[1] == broker_asset_id]
        for key in keys:
            del self.positions[key]
            self.skipped.append(
                SkippedRow(
                    "Positions", None, reason, {"broker_asset_id": broker_asset_id}
                )
            )


class BrokerAdapter(Protocol):
    broker_id: str
    broker_name: str
    timezone: ZoneInfo
    credential_keys: tuple[str, ...]

    def fetch_snapshot(self, credentials: Mapping[str, str]) -> Snapshot: ...
