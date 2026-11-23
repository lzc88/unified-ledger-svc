"""broker_connections

Revision ID: 9c1d4e7a2b60
Revises: bc544483898a
Create Date: 2026-11-23 12:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from user_config.crypto import UndecryptableValueError, decrypt, encrypt


# revision identifiers, used by Alembic.
revision: str = '9c1d4e7a2b60'
down_revision: Union[str, Sequence[str], None] = 'bc544483898a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IBKR_BROKER_ID = "IBKR"
IBKR_BROKER_NAME = "Interactive Brokers"
TOKEN_KEY = "IBKR_FLEX_TOKEN"
QUERY_ID_KEY = "IBKR_FLEX_QUERY_ID"
TOKEN_CREDENTIAL = "flex_token"
QUERY_ID_CREDENTIAL = "flex_query_id"
ACTIVE_STATUSES = "status IN ('PENDING', 'RUNNING')"

ORPHAN_ACCOUNTS = """
    SELECT a.account_id, a.from_broker_id
    FROM accounts a
    WHERE NOT EXISTS (
        SELECT 1 FROM broker_connections c
        WHERE c.from_user_id = a.from_user_id
          AND c.from_broker_id = a.from_broker_id
    )
"""

PURGE_ORPHANS = (
    f"""
    DELETE FROM trade_fees f
    USING executed_trades t, executed_trade_orders o
    WHERE f.from_trade_id = t.trade_id AND f.from_broker_id = t.from_broker_id
      AND t.from_trade_order_id = o.trade_order_id AND t.from_broker_id = o.from_broker_id
      AND (o.from_account_id, o.from_broker_id) IN ({ORPHAN_ACCOUNTS})
    """,
    f"""
    DELETE FROM executed_trades t
    USING executed_trade_orders o
    WHERE t.from_trade_order_id = o.trade_order_id AND t.from_broker_id = o.from_broker_id
      AND (o.from_account_id, o.from_broker_id) IN ({ORPHAN_ACCOUNTS})
    """,
    f"""
    DELETE FROM executed_trade_orders
    WHERE (from_account_id, from_broker_id) IN ({ORPHAN_ACCOUNTS})
    """,
    f"""
    DELETE FROM fx_fees f
    USING executed_fx x, executed_fx_orders o
    WHERE f.from_fx_id = x.fx_id AND f.from_broker_id = x.from_broker_id
      AND x.from_fx_order_id = o.fx_order_id AND x.from_broker_id = o.from_broker_id
      AND (o.from_account_id, o.from_broker_id) IN ({ORPHAN_ACCOUNTS})
    """,
    f"""
    DELETE FROM executed_fx x
    USING executed_fx_orders o
    WHERE x.from_fx_order_id = o.fx_order_id AND x.from_broker_id = o.from_broker_id
      AND (o.from_account_id, o.from_broker_id) IN ({ORPHAN_ACCOUNTS})
    """,
    f"""
    DELETE FROM executed_fx_orders
    WHERE (from_account_id, from_broker_id) IN ({ORPHAN_ACCOUNTS})
    """,
    f"""
    DELETE FROM executed_cash
    WHERE (from_account_id, from_broker_id) IN ({ORPHAN_ACCOUNTS})
    """,
    """
    DELETE FROM sync_jobs j
    WHERE NOT EXISTS (
        SELECT 1 FROM broker_connections c
        WHERE c.from_user_id = j.from_user_id
          AND c.from_broker_id = j.from_broker_id
    )
    """,
    """
    DELETE FROM accounts a
    WHERE NOT EXISTS (
        SELECT 1 FROM broker_connections c
        WHERE c.from_user_id = a.from_user_id
          AND c.from_broker_id = a.from_broker_id
    )
    """,
)


class BrokerConnectionMigrationError(RuntimeError):
    pass


def _decrypt(value: str, what: str) -> str:
    try:
        return decrypt(value)
    except UndecryptableValueError:
        raise BrokerConnectionMigrationError(
            f"can't decrypt {what}; check CONFIG_ENCRYPTION_KEY before migrating"
        ) from None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _move_ibkr_credentials_in(connection: sa.Connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT t.from_user_id, t.encrypted_value AS token, q.encrypted_value AS query_id
            FROM user_configs t
            JOIN user_configs q
              ON q.from_user_id = t.from_user_id AND q.config_key = :query_id_key
            WHERE t.config_key = :token_key
            """
        ),
        {"token_key": TOKEN_KEY, "query_id_key": QUERY_ID_KEY},
    ).all()

    if rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO brokers (broker_id, broker_name)
                VALUES (:broker_id, :broker_name)
                ON CONFLICT (broker_id) DO NOTHING
                """
            ),
            {"broker_id": IBKR_BROKER_ID, "broker_name": IBKR_BROKER_NAME},
        )

    for user_id, token, query_id in rows:
        credentials = {
            TOKEN_CREDENTIAL: _decrypt(token, f"{TOKEN_KEY} of {user_id}"),
            QUERY_ID_CREDENTIAL: _decrypt(query_id, f"{QUERY_ID_KEY} of {user_id}"),
        }
        connection.execute(
            sa.text(
                """
                INSERT INTO broker_connections (from_user_id, from_broker_id, credentials)
                VALUES (:user_id, :broker_id, :credentials)
                """
            ),
            {
                "user_id": user_id,
                "broker_id": IBKR_BROKER_ID,
                "credentials": encrypt(json.dumps(credentials)),
            },
        )

    connection.execute(
        sa.text("DELETE FROM user_configs WHERE config_key IN (:token_key, :query_id_key)"),
        {"token_key": TOKEN_KEY, "query_id_key": QUERY_ID_KEY},
    )


def _move_ibkr_credentials_out(connection: sa.Connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT from_user_id, credentials
            FROM broker_connections
            WHERE from_broker_id = :broker_id
            """
        ),
        {"broker_id": IBKR_BROKER_ID},
    ).all()

    for user_id, encrypted in rows:
        credentials = json.loads(_decrypt(encrypted, f"IBKR credentials of {user_id}"))
        for key, credential in ((TOKEN_KEY, TOKEN_CREDENTIAL), (QUERY_ID_KEY, QUERY_ID_CREDENTIAL)):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO user_configs (from_user_id, config_key, encrypted_value)
                    VALUES (:user_id, :key, :value)
                    """
                ),
                {"user_id": user_id, "key": key, "value": encrypt(credentials[credential])},
            )


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "broker_connections",
        sa.Column("from_user_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column("credentials", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["from_broker_id"],
            ["brokers.broker_id"],
            name=op.f("fk_broker_connections_from_broker_id_brokers"),
        ),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.user_id"],
            name=op.f("fk_broker_connections_from_user_id_users"),
        ),
        sa.PrimaryKeyConstraint(
            "from_user_id", "from_broker_id", name=op.f("pk_broker_connections")
        ),
    )

    connection = op.get_bind()
    _move_ibkr_credentials_in(connection)

    for statement in PURGE_ORPHANS:
        connection.execute(sa.text(statement))

    op.drop_index(
        "uq_sync_jobs_active_broker",
        table_name="sync_jobs",
        postgresql_where=sa.text(ACTIVE_STATUSES),
    )
    op.create_index(
        "uq_sync_jobs_active_connection",
        "sync_jobs",
        ["from_user_id", "from_broker_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_STATUSES),
    )

    op.create_foreign_key(
        op.f("fk_accounts_from_user_id_broker_connections"),
        "accounts",
        "broker_connections",
        ["from_user_id", "from_broker_id"],
        ["from_user_id", "from_broker_id"],
    )
    op.create_foreign_key(
        op.f("fk_sync_jobs_from_user_id_broker_connections"),
        "sync_jobs",
        "broker_connections",
        ["from_user_id", "from_broker_id"],
        ["from_user_id", "from_broker_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_sync_jobs_from_user_id_broker_connections"),
        "sync_jobs",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_accounts_from_user_id_broker_connections"),
        "accounts",
        type_="foreignkey",
    )

    op.drop_index(
        "uq_sync_jobs_active_connection",
        table_name="sync_jobs",
        postgresql_where=sa.text(ACTIVE_STATUSES),
    )
    op.create_index(
        "uq_sync_jobs_active_broker",
        "sync_jobs",
        ["from_broker_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_STATUSES),
    )

    _move_ibkr_credentials_out(op.get_bind())

    op.drop_table("broker_connections")
