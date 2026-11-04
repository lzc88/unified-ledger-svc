from sqlalchemy.orm import Session

from portfolio.ledger import CashFlow, Event, FxTrade, Trade
from portfolio.records import FxRecord, TradeRecord, user_records


def ledger_events(session: Session, user_id: str) -> list[Event]:
    records = user_records(session, user_id)
    return [
        *(
            CashFlow(row.tx_datetime, row.action, row.tx_amount, row.tx_currency)
            for row in records.cash
        ),
        *(_trade(record) for record in records.trades),
        *(_fx_trade(record) for record in records.fx),
    ]


def _trade(record: TradeRecord) -> Trade:
    trade, order, asset = record.trade, record.order, record.asset
    return Trade(
        at=trade.trade_datetime,
        asset_id=asset.trading_venue_figi,
        ticker=asset.ticker,
        category=asset.listing_category,
        exchange=asset.listing_exchange,
        action=order.action,
        quantity=trade.trade_quantity,
        amount=trade.trade_amount,
        currency=trade.trade_currency,
        fees=tuple((f.trade_fee_currency, f.trade_fee_amount) for f in record.fees),
    )


def _fx_trade(record: FxRecord) -> FxTrade:
    fx, order, pair = record.fx, record.order, record.pair
    return FxTrade(
        at=fx.fx_datetime,
        pair_id=pair.fx_pair_id,
        long_currency=pair.fx_long_currency,
        short_currency=pair.fx_short_currency,
        action=order.action,
        quantity=fx.fx_quantity,
        amount=fx.fx_amount,
        fees=tuple((f.fx_fee_currency, f.fx_fee_amount) for f in record.fees),
    )
