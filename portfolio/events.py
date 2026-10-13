from collections import defaultdict
from decimal import Decimal

from sqlalchemy import Select, select, tuple_
from sqlalchemy.orm import Session

from database.models import (
    Account,
    BrokerAsset,
    CanonicalAsset,
    CanonicalFx,
    ExecutedCash,
    ExecutedFx,
    ExecutedFxOrder,
    ExecutedTrade,
    ExecutedTradeOrder,
    FxFee,
    TradeFee,
)
from portfolio.ledger import CashFlow, Event, Fees, FxTrade, Trade

FeeKey = tuple[str, str]


def ledger_events(session: Session, user_id: str) -> list[Event]:
    accounts = select(Account.account_id, Account.from_broker_id).where(
        Account.from_user_id == user_id
    )
    return [
        *_cash_flows(session, accounts),
        *_trades(session, accounts),
        *_fx_trades(session, accounts),
    ]


def _cash_flows(session: Session, accounts: Select) -> list[CashFlow]:
    rows = session.scalars(
        select(ExecutedCash).where(
            tuple_(ExecutedCash.from_account_id, ExecutedCash.from_broker_id).in_(
                accounts
            )
        )
    )
    return [
        CashFlow(row.tx_datetime, row.action, row.tx_amount, row.tx_currency)
        for row in rows
    ]


def _trades(session: Session, accounts: Select) -> list[Trade]:
    of_user = tuple_(
        ExecutedTradeOrder.from_account_id, ExecutedTradeOrder.from_broker_id
    ).in_(accounts)
    order_of_trade = (
        ExecutedTradeOrder.trade_order_id == ExecutedTrade.from_trade_order_id
    ) & (ExecutedTradeOrder.from_broker_id == ExecutedTrade.from_broker_id)
    rows = session.execute(
        select(ExecutedTrade, ExecutedTradeOrder, CanonicalAsset)
        .join(ExecutedTradeOrder, order_of_trade)
        .join(
            BrokerAsset,
            (BrokerAsset.broker_asset_id == ExecutedTradeOrder.from_broker_asset_id)
            & (BrokerAsset.from_broker_id == ExecutedTradeOrder.from_broker_id),
        )
        .join(
            CanonicalAsset,
            CanonicalAsset.trading_venue_figi == BrokerAsset.from_asset_id,
        )
        .where(of_user)
    ).all()
    fee_rows = session.scalars(
        select(TradeFee)
        .join(
            ExecutedTrade,
            (ExecutedTrade.trade_id == TradeFee.from_trade_id)
            & (ExecutedTrade.from_broker_id == TradeFee.from_broker_id),
        )
        .join(ExecutedTradeOrder, order_of_trade)
        .where(of_user)
    )
    fees: defaultdict[FeeKey, list[tuple[str, Decimal]]] = defaultdict(list)
    for fee in fee_rows:
        fees[(fee.from_trade_id, fee.from_broker_id)].append(
            (fee.trade_fee_currency, fee.trade_fee_amount)
        )
    return [
        Trade(
            at=trade.trade_datetime,
            asset_id=asset.trading_venue_figi,
            ticker=asset.ticker,
            category=asset.listing_category,
            exchange=asset.listing_exchange,
            action=order.action,
            quantity=trade.trade_quantity,
            amount=trade.trade_amount,
            currency=trade.trade_currency,
            fees=_fees(fees, trade.trade_id, trade.from_broker_id),
        )
        for trade, order, asset in rows
    ]


def _fx_trades(session: Session, accounts: Select) -> list[FxTrade]:
    of_user = tuple_(
        ExecutedFxOrder.from_account_id, ExecutedFxOrder.from_broker_id
    ).in_(accounts)
    order_of_fx = (ExecutedFxOrder.fx_order_id == ExecutedFx.from_fx_order_id) & (
        ExecutedFxOrder.from_broker_id == ExecutedFx.from_broker_id
    )
    rows = session.execute(
        select(ExecutedFx, ExecutedFxOrder, CanonicalFx)
        .join(ExecutedFxOrder, order_of_fx)
        .join(CanonicalFx, CanonicalFx.fx_pair_id == ExecutedFxOrder.from_fx_pair_id)
        .where(of_user)
    ).all()
    fee_rows = session.scalars(
        select(FxFee)
        .join(
            ExecutedFx,
            (ExecutedFx.fx_id == FxFee.from_fx_id)
            & (ExecutedFx.from_broker_id == FxFee.from_broker_id),
        )
        .join(ExecutedFxOrder, order_of_fx)
        .where(of_user)
    )
    fees: defaultdict[FeeKey, list[tuple[str, Decimal]]] = defaultdict(list)
    for fee in fee_rows:
        fees[(fee.from_fx_id, fee.from_broker_id)].append(
            (fee.fx_fee_currency, fee.fx_fee_amount)
        )
    return [
        FxTrade(
            at=fx.fx_datetime,
            pair_id=pair.fx_pair_id,
            long_currency=pair.fx_long_currency,
            short_currency=pair.fx_short_currency,
            action=order.action,
            quantity=fx.fx_quantity,
            amount=fx.fx_amount,
            fees=_fees(fees, fx.fx_id, fx.from_broker_id),
        )
        for fx, order, pair in rows
    ]


def _fees(
    fees: dict[FeeKey, list[tuple[str, Decimal]]], row_id: str, broker_id: str
) -> Fees:
    return tuple(fees.get((row_id, broker_id), ()))
