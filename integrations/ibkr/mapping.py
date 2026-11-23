import re
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation

from config.config import (
    IBKR_LISTING_EXCHANGE_TO_EXCH_CODES,
    IBKR_SUB_CATEGORY_TO_LISTING_CATEGORY,
)
from database.models import ListingCategory
from integrations.base import AssetIdentity, FormatError, SkippedRow, Snapshot

POSITIONS_SECTION = "OpenPositions"
CASH_SECTION = "CashReport"

TRACKED_ASSET_CATEGORY = "STK"
POSITION_LEVEL_OF_DETAIL = "SUMMARY"
BASE_SUMMARY_CURRENCY = "BASE_SUMMARY"


class FlexFormatError(FormatError):
    pass


class _Skip(Exception):
    pass


def map_snapshot(document: bytes) -> Snapshot:

    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise FlexFormatError(f"Flex statement is not valid XML: {exc}") from None

    if root.tag != "FlexQueryResponse":
        raise FlexFormatError(f"Expected FlexQueryResponse, got <{root.tag}>")

    snapshot = Snapshot()

    for statement in root.iter("FlexStatement"):
        _map_statement(snapshot, statement)

        statement_date = _statement_date(statement)
        if statement_date is None:
            continue

        if snapshot.as_of is None or statement_date > snapshot.as_of:
            snapshot.as_of = statement_date

    return snapshot


def _statement_date(statement: ET.Element) -> date | None:

    raw = statement.get("toDate", "").strip()
    if not raw:
        return None

    digits = re.sub(r"\D", "", raw)

    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        raise FlexFormatError(
            f"FlexStatement toDate={raw!r} is not a yyyyMMdd date"
        ) from None


def _map_statement(snapshot: Snapshot, statement: ET.Element) -> None:

    account_id = _require(statement.attrib, "accountId", "FlexStatement")
    snapshot.accounts.setdefault(account_id, {"account_id": account_id})

    info = statement.find("AccountInformation")
    if info is not None and info.get("name", "").strip():
        snapshot.account_names[account_id] = info.get("name", "").strip()

    positions = _section(statement, POSITIONS_SECTION, "Open Positions")
    rows = positions.findall("OpenPosition")
    summaries = [
        element
        for element in rows
        if element.get("levelOfDetail", POSITION_LEVEL_OF_DETAIL) == POSITION_LEVEL_OF_DETAIL
    ]
    if rows and not summaries:
        raise FlexFormatError(
            "Open Positions has no SUMMARY rows; set its level of detail to "
            "Summary in the Flex Query"
        )

    for element in summaries:

        attrs = dict(element.attrib)
        try:
            _map_position(snapshot, attrs, account_id)
        except _Skip as skip:
            snapshot.skipped.append(
                SkippedRow(POSITIONS_SECTION, attrs.get("conid"), str(skip), attrs)
            )

    cash = _section(statement, CASH_SECTION, "Cash Report")
    for element in cash.findall("CashReportCurrency"):
        _map_cash(snapshot, dict(element.attrib), account_id)


def _section(statement: ET.Element, tag: str, label: str) -> ET.Element:

    section = statement.find(tag)

    if section is None:
        raise FlexFormatError(
            f"Flex statement has no {tag} section; add {label} to the Flex Query"
        )

    return section


def _map_position(snapshot: Snapshot, attrs: dict[str, str], account_id: str) -> None:

    section = POSITIONS_SECTION
    asset_category = _require(attrs, "assetCategory", section)

    if asset_category != TRACKED_ASSET_CATEGORY:
        raise _Skip(f"asset category {asset_category!r} is not tracked")

    category = _listing_category(attrs)

    quantity = _decimal(attrs, "position", section)
    if quantity == 0:
        raise _Skip("zero quantity")

    conid = _require(attrs, "conid", section)
    currency = _require(attrs, "currency", section)
    symbol = _require(attrs, "symbol", section)
    listing_exchange = _require(attrs, "listingExchange", section)
    cost_basis = _decimal(attrs, "costBasisMoney", section)

    snapshot.assets.setdefault(
        conid, {"listing_category": category, "listing_currency": currency}
    )

    snapshot.identities.setdefault(
        conid,
        AssetIdentity(
            symbol=symbol,
            currency=currency,
            exch_codes=IBKR_LISTING_EXCHANGE_TO_EXCH_CODES.get(
                listing_exchange, frozenset()
            ),
            isin=attrs.get("isin", "").strip() or None,
        ),
    )

    snapshot.positions.setdefault(
        (account_id, conid),
        {
            "from_account_id": account_id,
            "from_broker_asset_id": conid,
            "quantity": quantity,
            "cost_basis": cost_basis,
            "currency": currency,
        },
    )


def _map_cash(snapshot: Snapshot, attrs: dict[str, str], account_id: str) -> None:

    section = CASH_SECTION
    currency = _require(attrs, "currency", section)

    if currency == BASE_SUMMARY_CURRENCY:
        return

    balance = _decimal(attrs, "endingCash", section)
    if balance == 0:
        return

    snapshot.cash.setdefault(
        (account_id, currency),
        {"from_account_id": account_id, "currency": currency, "balance": balance},
    )


def _listing_category(attrs: dict[str, str]) -> ListingCategory:

    sub_category = _require(attrs, "subCategory", POSITIONS_SECTION)
    category = IBKR_SUB_CATEGORY_TO_LISTING_CATEGORY.get(sub_category)

    if category is None:
        raise _Skip(f"sub category {sub_category!r} is not tracked")

    return ListingCategory(category)


def _require(attrs: dict[str, str], name: str, section: str) -> str:

    value = attrs.get(name)

    if value is None:
        raise FlexFormatError(
            f"{section} rows have no {name!r} field; add it to the Flex Query"
        )

    return value.strip()


def _decimal(attrs: dict[str, str], name: str, section: str) -> Decimal:

    raw = _require(attrs, name, section)

    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        raise FlexFormatError(f"{section} {name}={raw!r} is not a number") from None
