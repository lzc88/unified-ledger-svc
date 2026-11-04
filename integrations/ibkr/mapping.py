import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from datetime import datetime
from decimal import Decimal, InvalidOperation

from config.config import (
    IBKR_FLEX_DATE_FORMATS,
    IBKR_FLEX_TIME_FORMATS,
    IBKR_FLEX_TIMEZONE,
    IBKR_LISTING_EXCHANGE_TO_EXCH_CODES,
    IBKR_SUB_CATEGORY_TO_LISTING_CATEGORY,
)
from database.models import CashAction, FeeType, ListingCategory, OrderAction
from integrations.base import AssetIdentity, FormatError, MappingResult, Row, SkippedRow

FX_PAIR_PATTERN = re.compile(r"^([A-Z]{3})\.([A-Z]{3})$")


class FlexFormatError(FormatError):
    pass


class _Skip(Exception):
    pass


Mapper = Callable[[MappingResult, dict[str, str], str], None]


def map_statements(documents: Iterable[bytes]) -> MappingResult:

    result = MappingResult()
    skipped_ids: set[str] = set()

    for document in documents:

        try:
            root = ET.fromstring(document)
        except ET.ParseError as exc:
            raise FlexFormatError(f"Flex statement is not valid XML: {exc}") from None

        if root.tag != "FlexQueryResponse":
            raise FlexFormatError(f"Expected FlexQueryResponse, got <{root.tag}>")

        for statement in root.iter("FlexStatement"):

            account_id = _require(statement.attrib, "accountId", "FlexStatement")
            result.accounts.setdefault(account_id, {"account_id": account_id})
            info = statement.find("AccountInformation")

            if info is not None and info.get("name", "").strip():
                result.account_names[account_id] = info.get("name", "").strip()

            for element in statement.findall("Trades/Trade"):
                if element.get("levelOfDetail", "EXECUTION") == "EXECUTION":
                    _apply(
                        result, skipped_ids, "Trades", element, account_id, _map_trade
                    )

            for element in statement.findall("CashTransactions/CashTransaction"):
                if element.get("levelOfDetail", "DETAIL") == "DETAIL":
                    _apply(
                        result,
                        skipped_ids,
                        "CashTransactions",
                        element,
                        account_id,
                        _map_cash_transaction,
                    )

    return result


def _apply(
    result: MappingResult,
    skipped_ids: set[str],
    section: str,
    element: ET.Element,
    account_id: str,
    mapper: Mapper,
) -> None:

    attrs = dict(element.attrib)

    try:
        mapper(result, attrs, account_id)
    except _Skip as skip:
        txn_id = attrs.get("transactionID") or attrs.get("tradeID")
        if txn_id is not None and txn_id in skipped_ids:
            return
        result.skipped.append(SkippedRow(section, txn_id, str(skip), attrs))
        if txn_id is not None:
            skipped_ids.add(txn_id)


def _map_trade(result: MappingResult, attrs: dict[str, str], account_id: str) -> None:

    section = "Trades"
    trade_id = _require(attrs, "tradeID", section)

    if trade_id in result.trades or trade_id in result.fx:
        return

    category = _require(attrs, "assetCategory", section)

    if category == "CASH":
        _map_fx(result, attrs, account_id, trade_id)

    elif category == "STK":
        _map_stock(result, attrs, account_id, trade_id)

    else:
        raise _Skip(f"asset category {category!r} is not tracked")


def _map_stock(
    result: MappingResult, attrs: dict[str, str], account_id: str, trade_id: str
) -> None:

    section = "Trades"
    category = _listing_category(attrs)
    quantity, action, order_id = _execution(attrs)
    fees = _fees(attrs)

    conid = _require(attrs, "conid", section)
    listing_exchange = _optional(attrs, "listingExchange", section)
    currency = _require(attrs, "currency", section)
    result.assets.setdefault(
        conid, {"listing_category": category, "listing_currency": currency}
    )

    result.identities.setdefault(
        conid,
        AssetIdentity(
            symbol=_require(attrs, "symbol", section),
            currency=currency,
            exch_codes=IBKR_LISTING_EXCHANGE_TO_EXCH_CODES.get(
                listing_exchange or "", frozenset()
            ),
            isin=attrs.get("isin", "").strip() or None,
        ),
    )

    result.trade_orders.setdefault(
        order_id,
        {
            "trade_order_id": order_id,
            "from_account_id": account_id,
            "from_broker_asset_id": conid,
            "action": action,
            "order_datetime": _datetime(attrs, "orderTime", section),
        },
    )
    result.trades[trade_id] = {
        "trade_id": trade_id,
        "from_trade_order_id": order_id,
        "trade_amount": abs(_decimal(attrs, "proceeds", section)),
        "trade_quantity": abs(quantity),
        "trade_price": _decimal(attrs, "tradePrice", section),
        "trade_currency": currency,
        "trade_datetime": _datetime(attrs, "dateTime", section),
    }
    for fee_type, (amount, fee_currency) in fees.items():
        result.trade_fees[(trade_id, fee_type)] = {
            "from_trade_id": trade_id,
            "trade_fee_type": fee_type,
            "trade_fee_amount": amount,
            "trade_fee_currency": fee_currency,
        }


def _map_fx(
    result: MappingResult, attrs: dict[str, str], account_id: str, trade_id: str
) -> None:
    section = "Trades"
    symbol = _require(attrs, "symbol", section)
    pair = FX_PAIR_PATTERN.match(symbol)
    if pair is None:
        raise _Skip(f"FX symbol {symbol!r} is not of the form BASE.QUOTE")
    quantity, action, order_id = _execution(attrs)
    fees = _fees(attrs)

    result.fx_pairs.setdefault(
        symbol,
        {
            "fx_pair_id": symbol,
            "fx_long_currency": pair[1],
            "fx_short_currency": pair[2],
        },
    )
    result.fx_orders.setdefault(
        order_id,
        {
            "fx_order_id": order_id,
            "from_account_id": account_id,
            "from_fx_pair_id": symbol,
            "action": action,
            "order_datetime": _datetime(attrs, "orderTime", section),
        },
    )
    result.fx[trade_id] = {
        "fx_id": trade_id,
        "from_fx_order_id": order_id,
        "fx_amount": abs(_decimal(attrs, "proceeds", section)),
        "fx_quantity": abs(quantity),
        "fx_price": _decimal(attrs, "tradePrice", section),
        "fx_datetime": _datetime(attrs, "dateTime", section),
    }
    for fee_type, (amount, fee_currency) in fees.items():
        result.fx_fees[(trade_id, fee_type)] = {
            "from_fx_id": trade_id,
            "fx_fee_type": fee_type,
            "fx_fee_amount": amount,
            "fx_fee_currency": fee_currency,
        }


def _listing_category(attrs: dict[str, str]) -> ListingCategory:
    sub_category = _require(attrs, "subCategory", "Trades")
    category = IBKR_SUB_CATEGORY_TO_LISTING_CATEGORY.get(sub_category)
    if category is None:
        raise _Skip(f"sub category {sub_category!r} is not tracked")
    return ListingCategory(category)


def _execution(attrs: dict[str, str]) -> tuple[Decimal, OrderAction, str]:
    quantity = _decimal(attrs, "quantity", "Trades")
    if quantity == 0:
        raise _Skip("zero quantity")
    action = _order_action(attrs)
    order_id = _require(attrs, "ibOrderID", "Trades")
    if not order_id or order_id == "0":
        raise _Skip("no ibOrderID")
    return quantity, action, order_id


def _order_action(attrs: dict[str, str]) -> OrderAction:
    buy_sell = _require(attrs, "buySell", "Trades")
    try:
        return OrderAction(buy_sell)
    except ValueError:
        raise _Skip(f"buySell {buy_sell!r} is not BUY/SELL") from None


def _fees(attrs: dict[str, str]) -> dict[FeeType, tuple[Decimal, str]]:
    currency = _require(attrs, "ibCommissionCurrency", "Trades")
    fees = {}
    for fee_type, name in (
        (FeeType.COMMISSION, "ibCommission"),
        (FeeType.TAX, "taxes"),
    ):
        amount = _decimal(attrs, name, "Trades")
        if amount > 0:
            raise _Skip(f"positive {name} {amount} (rebate) is not supported")
        if amount < 0:
            fees[fee_type] = (-amount, currency)
    return fees


def _map_cash_transaction(
    result: MappingResult, attrs: dict[str, str], account_id: str
) -> None:
    section = "CashTransactions"
    kind = _require(attrs, "type", section)
    if kind != "Deposits/Withdrawals":
        raise _Skip(f"cash transaction type {kind!r} is not tracked")
    tx_id = _require(attrs, "transactionID", section)
    if tx_id in result.cash:
        return
    amount = _decimal(attrs, "amount", section)
    if amount == 0:
        raise _Skip("zero amount")
    result.cash[tx_id] = {
        "cash_id": tx_id,
        "from_account_id": account_id,
        "tx_datetime": _datetime(attrs, "dateTime", section),
        "action": CashAction.DEPOSIT if amount > 0 else CashAction.WITHDRAW,
        "tx_amount": abs(amount),
        "tx_currency": _require(attrs, "currency", section),
    }


def _require(attrs: dict[str, str], name: str, section: str) -> str:
    value = attrs.get(name)
    if value is None:
        raise FlexFormatError(
            f"{section} rows have no {name!r} field; add it to the Flex Query"
        )
    return value.strip()


def _optional(attrs: dict[str, str], name: str, section: str) -> str | None:
    return _require(attrs, name, section) or None


def _decimal(attrs: dict[str, str], name: str, section: str) -> Decimal:
    raw = _require(attrs, name, section)
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        raise FlexFormatError(f"{section} {name}={raw!r} is not a number") from None


def _datetime(attrs: dict[str, str], name: str, section: str) -> datetime:
    raw = _require(attrs, name, section)
    normalized = raw
    for separator in (",", " ", "T"):
        normalized = normalized.replace(separator, ";")
    day_part, _, time_part = normalized.partition(";")
    day = _parse(day_part, IBKR_FLEX_DATE_FORMATS)
    clock = _parse(time_part, IBKR_FLEX_TIME_FORMATS) if time_part else datetime.min
    if day is None or clock is None:
        raise FlexFormatError(
            f"{section} {name}={raw!r}: set the Flex Query date format to yyyyMMdd "
            "and time format to HHmmss or HH:mm:ss"
        )
    return datetime.combine(day.date(), clock.time(), tzinfo=IBKR_FLEX_TIMEZONE)


def _parse(value: str, formats: tuple[str, ...]) -> datetime | None:
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
