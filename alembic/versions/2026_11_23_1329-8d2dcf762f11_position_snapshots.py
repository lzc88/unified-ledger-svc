"""position snapshots

Revision ID: 8d2dcf762f11
Revises: 9c1d4e7a2b60
Create Date: 2026-11-23 13:29:25.203444

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8d2dcf762f11'
down_revision: Union[str, Sequence[str], None] = '9c1d4e7a2b60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('account_snapshots',
    sa.Column('snapshot_date', sa.Date(), nullable=False),
    sa.Column('from_broker_id', sa.String(length=100), nullable=False),
    sa.Column('from_account_id', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['from_account_id', 'from_broker_id'], ['accounts.account_id', 'accounts.from_broker_id'], name=op.f('fk_account_snapshots_from_account_id_accounts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('snapshot_date', 'from_broker_id', 'from_account_id', name=op.f('pk_account_snapshots'))
    )
    op.create_index('ix_account_snapshots_account_date', 'account_snapshots', ['from_account_id', 'from_broker_id', 'snapshot_date'], unique=False)
    op.create_table('cash_snapshots',
    sa.Column('snapshot_date', sa.Date(), nullable=False),
    sa.Column('from_broker_id', sa.String(length=100), nullable=False),
    sa.Column('from_account_id', sa.String(length=100), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('balance', sa.Numeric(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f('ck_cash_snapshots_currency_iso')),
    sa.ForeignKeyConstraint(['from_account_id', 'from_broker_id'], ['accounts.account_id', 'accounts.from_broker_id'], name=op.f('fk_cash_snapshots_from_account_id_accounts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('snapshot_date', 'from_broker_id', 'from_account_id', 'currency', name=op.f('pk_cash_snapshots'))
    )
    op.create_index('ix_cash_snapshots_account_date', 'cash_snapshots', ['from_account_id', 'from_broker_id', 'snapshot_date'], unique=False)
    op.create_table('position_snapshots',
    sa.Column('snapshot_date', sa.Date(), nullable=False),
    sa.Column('from_broker_id', sa.String(length=100), nullable=False),
    sa.Column('from_account_id', sa.String(length=100), nullable=False),
    sa.Column('from_broker_asset_id', sa.String(length=100), nullable=False),
    sa.Column('quantity', sa.Numeric(), nullable=False),
    sa.Column('cost_basis', sa.Numeric(), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f('ck_position_snapshots_currency_iso')),
    sa.CheckConstraint('quantity <> 0', name=op.f('ck_position_snapshots_quantity_non_zero')),
    sa.ForeignKeyConstraint(['from_account_id', 'from_broker_id'], ['accounts.account_id', 'accounts.from_broker_id'], name=op.f('fk_position_snapshots_from_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['from_broker_asset_id', 'from_broker_id'], ['broker_assets.broker_asset_id', 'broker_assets.from_broker_id'], name=op.f('fk_position_snapshots_from_broker_asset_id_broker_assets')),
    sa.PrimaryKeyConstraint('snapshot_date', 'from_broker_id', 'from_account_id', 'from_broker_asset_id', name=op.f('pk_position_snapshots'))
    )
    op.create_index('ix_position_snapshots_account_date', 'position_snapshots', ['from_account_id', 'from_broker_id', 'snapshot_date'], unique=False)
    op.drop_table('trade_fees')
    op.drop_index(op.f('ix_executed_trades_order'), table_name='executed_trades')
    op.drop_table('executed_trades')
    op.drop_index(op.f('ix_executed_trade_orders_account'), table_name='executed_trade_orders')
    op.drop_index(op.f('ix_executed_trade_orders_broker_asset'), table_name='executed_trade_orders')
    op.drop_table('executed_trade_orders')
    op.drop_index(op.f('ix_executed_cash_account'), table_name='executed_cash')
    op.drop_table('executed_cash')
    op.drop_table('fx_fees')
    op.drop_index(op.f('ix_executed_fx_order'), table_name='executed_fx')
    op.drop_table('executed_fx')
    op.drop_index(op.f('ix_executed_fx_orders_account'), table_name='executed_fx_orders')
    op.drop_index(op.f('ix_executed_fx_orders_from_fx_pair_id'), table_name='executed_fx_orders')
    op.drop_table('executed_fx_orders')
    op.drop_table('canonical_fx')
    op.drop_index(op.f('ix_sync_jobs_from_user_id'), table_name='sync_jobs')
    op.drop_index(op.f('uq_sync_jobs_active_connection'), table_name='sync_jobs', postgresql_where="((status)::text = ANY ((ARRAY['PENDING'::character varying, 'RUNNING'::character varying])::text[]))")
    op.drop_table('sync_jobs')
    op.add_column('broker_connections', sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('broker_connections', sa.Column('last_sync_status', sa.Enum('RUNNING', 'SUCCEEDED', 'FAILED', name='last_sync_status', native_enum=False, create_constraint=True, length=16), nullable=True))
    op.add_column('broker_connections', sa.Column('last_sync_error', sa.Text(), nullable=True))
    op.add_column('broker_connections', sa.Column('last_sync_started_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('broker_connections', 'last_sync_started_at')
    op.drop_column('broker_connections', 'last_sync_error')
    op.drop_column('broker_connections', 'last_sync_status')
    op.drop_column('broker_connections', 'last_synced_at')
    op.create_table('sync_jobs',
    sa.Column('job_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('from_user_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_broker_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('kind', sa.VARCHAR(length=16), autoincrement=False, nullable=False),
    sa.Column('status', sa.VARCHAR(length=16), autoincrement=False, nullable=False),
    sa.Column('start_date', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('end_date', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('inserted', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('skipped', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('error', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('finished_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("kind::text = ANY (ARRAY['BACKFILL'::character varying, 'REFRESH'::character varying]::text[])", name=op.f('ck_sync_jobs_kind')),
    sa.CheckConstraint("status::text = ANY (ARRAY['PENDING'::character varying, 'RUNNING'::character varying, 'SUCCEEDED'::character varying, 'FAILED'::character varying]::text[])", name=op.f('ck_sync_jobs_status')),
    sa.CheckConstraint('start_date <= end_date', name=op.f('ck_sync_jobs_date_range')),
    sa.ForeignKeyConstraint(['from_broker_id'], ['brokers.broker_id'], name=op.f('fk_sync_jobs_from_broker_id_brokers')),
    sa.ForeignKeyConstraint(['from_user_id', 'from_broker_id'], ['broker_connections.from_user_id', 'broker_connections.from_broker_id'], name=op.f('fk_sync_jobs_from_user_id_broker_connections')),
    sa.ForeignKeyConstraint(['from_user_id'], ['users.user_id'], name=op.f('fk_sync_jobs_from_user_id_users')),
    sa.PrimaryKeyConstraint('job_id', name=op.f('pk_sync_jobs'))
    )
    op.create_index(op.f('uq_sync_jobs_active_connection'), 'sync_jobs', ['from_user_id', 'from_broker_id'], unique=True, postgresql_where="((status)::text = ANY ((ARRAY['PENDING'::character varying, 'RUNNING'::character varying])::text[]))")
    op.create_index(op.f('ix_sync_jobs_from_user_id'), 'sync_jobs', ['from_user_id'], unique=False)
    op.create_table('canonical_fx',
    sa.Column('fx_pair_id', sa.VARCHAR(length=16), autoincrement=False, nullable=False),
    sa.Column('fx_long_currency', sa.CHAR(length=3), autoincrement=False, nullable=False),
    sa.Column('fx_short_currency', sa.CHAR(length=3), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("fx_long_currency ~ '^[A-Z]{3}$'::text", name=op.f('ck_canonical_fx_fx_long_currency_iso')),
    sa.CheckConstraint("fx_short_currency ~ '^[A-Z]{3}$'::text", name=op.f('ck_canonical_fx_fx_short_currency_iso')),
    sa.PrimaryKeyConstraint('fx_pair_id', name=op.f('pk_canonical_fx'))
    )
    op.create_table('executed_fx_orders',
    sa.Column('fx_order_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_broker_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_account_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_fx_pair_id', sa.VARCHAR(length=16), autoincrement=False, nullable=False),
    sa.Column('action', sa.VARCHAR(length=16), autoincrement=False, nullable=False),
    sa.Column('order_datetime', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("action::text = ANY (ARRAY['BUY'::character varying, 'SELL'::character varying]::text[])", name=op.f('ck_executed_fx_orders_action')),
    sa.ForeignKeyConstraint(['from_account_id', 'from_broker_id'], ['accounts.account_id', 'accounts.from_broker_id'], name=op.f('fk_executed_fx_orders_from_account_id_accounts')),
    sa.ForeignKeyConstraint(['from_fx_pair_id'], ['canonical_fx.fx_pair_id'], name=op.f('fk_executed_fx_orders_from_fx_pair_id_canonical_fx')),
    sa.PrimaryKeyConstraint('fx_order_id', 'from_broker_id', name=op.f('pk_executed_fx_orders'))
    )
    op.create_index(op.f('ix_executed_fx_orders_from_fx_pair_id'), 'executed_fx_orders', ['from_fx_pair_id'], unique=False)
    op.create_index(op.f('ix_executed_fx_orders_account'), 'executed_fx_orders', ['from_account_id', 'from_broker_id'], unique=False)
    op.create_table('executed_fx',
    sa.Column('fx_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_broker_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_fx_order_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('fx_amount', sa.NUMERIC(), autoincrement=False, nullable=False),
    sa.Column('fx_quantity', sa.NUMERIC(), autoincrement=False, nullable=False),
    sa.Column('fx_price', sa.NUMERIC(), autoincrement=False, nullable=False),
    sa.Column('fx_datetime', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint('fx_amount >= 0::numeric', name=op.f('ck_executed_fx_fx_amount_non_negative')),
    sa.CheckConstraint('fx_price >= 0::numeric', name=op.f('ck_executed_fx_fx_price_non_negative')),
    sa.CheckConstraint('fx_quantity > 0::numeric', name=op.f('ck_executed_fx_fx_quantity_positive')),
    sa.ForeignKeyConstraint(['from_fx_order_id', 'from_broker_id'], ['executed_fx_orders.fx_order_id', 'executed_fx_orders.from_broker_id'], name=op.f('fk_executed_fx_from_fx_order_id_executed_fx_orders')),
    sa.PrimaryKeyConstraint('fx_id', 'from_broker_id', name=op.f('pk_executed_fx'))
    )
    op.create_index(op.f('ix_executed_fx_order'), 'executed_fx', ['from_fx_order_id', 'from_broker_id'], unique=False)
    op.create_table('fx_fees',
    sa.Column('from_fx_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_broker_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('fx_fee_type', sa.VARCHAR(length=16), autoincrement=False, nullable=False),
    sa.Column('fx_fee_amount', sa.NUMERIC(), autoincrement=False, nullable=False),
    sa.Column('fx_fee_currency', sa.CHAR(length=3), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("fx_fee_currency ~ '^[A-Z]{3}$'::text", name=op.f('ck_fx_fees_fx_fee_currency_iso')),
    sa.CheckConstraint("fx_fee_type::text = ANY (ARRAY['COMMISSION'::character varying, 'TAX'::character varying]::text[])", name=op.f('ck_fx_fees_fx_fee_type')),
    sa.CheckConstraint('fx_fee_amount > 0::numeric', name=op.f('ck_fx_fees_fx_fee_amount_positive')),
    sa.ForeignKeyConstraint(['from_fx_id', 'from_broker_id'], ['executed_fx.fx_id', 'executed_fx.from_broker_id'], name=op.f('fk_fx_fees_from_fx_id_executed_fx')),
    sa.PrimaryKeyConstraint('from_fx_id', 'from_broker_id', 'fx_fee_type', name=op.f('pk_fx_fees'))
    )
    op.create_table('executed_cash',
    sa.Column('cash_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_broker_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_account_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('tx_datetime', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('action', sa.VARCHAR(length=16), autoincrement=False, nullable=False),
    sa.Column('tx_amount', sa.NUMERIC(), autoincrement=False, nullable=False),
    sa.Column('tx_currency', sa.CHAR(length=3), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("action::text = ANY (ARRAY['DEPOSIT'::character varying, 'WITHDRAW'::character varying]::text[])", name=op.f('ck_executed_cash_action')),
    sa.CheckConstraint("tx_currency ~ '^[A-Z]{3}$'::text", name=op.f('ck_executed_cash_tx_currency_iso')),
    sa.CheckConstraint('tx_amount > 0::numeric', name=op.f('ck_executed_cash_tx_amount_positive')),
    sa.ForeignKeyConstraint(['from_account_id', 'from_broker_id'], ['accounts.account_id', 'accounts.from_broker_id'], name=op.f('fk_executed_cash_from_account_id_accounts')),
    sa.PrimaryKeyConstraint('cash_id', 'from_broker_id', name=op.f('pk_executed_cash'))
    )
    op.create_index(op.f('ix_executed_cash_account'), 'executed_cash', ['from_account_id', 'from_broker_id'], unique=False)
    op.create_table('executed_trade_orders',
    sa.Column('trade_order_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_broker_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_account_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_broker_asset_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('action', sa.VARCHAR(length=16), autoincrement=False, nullable=False),
    sa.Column('order_datetime', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("action::text = ANY (ARRAY['BUY'::character varying, 'SELL'::character varying]::text[])", name=op.f('ck_executed_trade_orders_action')),
    sa.ForeignKeyConstraint(['from_account_id', 'from_broker_id'], ['accounts.account_id', 'accounts.from_broker_id'], name=op.f('fk_executed_trade_orders_from_account_id_accounts')),
    sa.ForeignKeyConstraint(['from_broker_asset_id', 'from_broker_id'], ['broker_assets.broker_asset_id', 'broker_assets.from_broker_id'], name=op.f('fk_executed_trade_orders_from_broker_asset_id_broker_assets')),
    sa.PrimaryKeyConstraint('trade_order_id', 'from_broker_id', name=op.f('pk_executed_trade_orders'))
    )
    op.create_index(op.f('ix_executed_trade_orders_broker_asset'), 'executed_trade_orders', ['from_broker_asset_id', 'from_broker_id'], unique=False)
    op.create_index(op.f('ix_executed_trade_orders_account'), 'executed_trade_orders', ['from_account_id', 'from_broker_id'], unique=False)
    op.create_table('executed_trades',
    sa.Column('trade_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_broker_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_trade_order_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('trade_amount', sa.NUMERIC(), autoincrement=False, nullable=False),
    sa.Column('trade_quantity', sa.NUMERIC(), autoincrement=False, nullable=False),
    sa.Column('trade_price', sa.NUMERIC(), autoincrement=False, nullable=False),
    sa.Column('trade_currency', sa.CHAR(length=3), autoincrement=False, nullable=False),
    sa.Column('trade_datetime', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("trade_currency ~ '^[A-Z]{3}$'::text", name=op.f('ck_executed_trades_trade_currency_iso')),
    sa.CheckConstraint('trade_amount >= 0::numeric', name=op.f('ck_executed_trades_trade_amount_non_negative')),
    sa.CheckConstraint('trade_price >= 0::numeric', name=op.f('ck_executed_trades_trade_price_non_negative')),
    sa.CheckConstraint('trade_quantity > 0::numeric', name=op.f('ck_executed_trades_trade_quantity_positive')),
    sa.ForeignKeyConstraint(['from_trade_order_id', 'from_broker_id'], ['executed_trade_orders.trade_order_id', 'executed_trade_orders.from_broker_id'], name=op.f('fk_executed_trades_from_trade_order_id_executed_trade_orders')),
    sa.PrimaryKeyConstraint('trade_id', 'from_broker_id', name=op.f('pk_executed_trades'))
    )
    op.create_index(op.f('ix_executed_trades_order'), 'executed_trades', ['from_trade_order_id', 'from_broker_id'], unique=False)
    op.create_table('trade_fees',
    sa.Column('from_trade_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('from_broker_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('trade_fee_type', sa.VARCHAR(length=16), autoincrement=False, nullable=False),
    sa.Column('trade_fee_amount', sa.NUMERIC(), autoincrement=False, nullable=False),
    sa.Column('trade_fee_currency', sa.CHAR(length=3), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("trade_fee_currency ~ '^[A-Z]{3}$'::text", name=op.f('ck_trade_fees_trade_fee_currency_iso')),
    sa.CheckConstraint("trade_fee_type::text = ANY (ARRAY['COMMISSION'::character varying, 'TAX'::character varying]::text[])", name=op.f('ck_trade_fees_trade_fee_type')),
    sa.CheckConstraint('trade_fee_amount > 0::numeric', name=op.f('ck_trade_fees_trade_fee_amount_positive')),
    sa.ForeignKeyConstraint(['from_trade_id', 'from_broker_id'], ['executed_trades.trade_id', 'executed_trades.from_broker_id'], name=op.f('fk_trade_fees_from_trade_id_executed_trades')),
    sa.PrimaryKeyConstraint('from_trade_id', 'from_broker_id', 'trade_fee_type', name=op.f('pk_trade_fees'))
    )
    op.drop_index('ix_position_snapshots_account_date', table_name='position_snapshots')
    op.drop_table('position_snapshots')
    op.drop_index('ix_cash_snapshots_account_date', table_name='cash_snapshots')
    op.drop_table('cash_snapshots')
    op.drop_index('ix_account_snapshots_account_date', table_name='account_snapshots')
    op.drop_table('account_snapshots')
