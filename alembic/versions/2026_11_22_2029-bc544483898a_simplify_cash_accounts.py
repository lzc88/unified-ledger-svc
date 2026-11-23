"""simplify_cash_accounts

Revision ID: bc544483898a
Revises: 55f7381d3ac3
Create Date: 2026-11-22 20:29:43.602869

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bc544483898a'
down_revision: Union[str, Sequence[str], None] = '55f7381d3ac3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENCIES = ("SGD", "USD", "EUR", "GBP", "JPY", "AUD", "HKD", "CNY", "MYR")
CURRENCY_LIST = ", ".join(f"'{currency}'" for currency in CURRENCIES)
LABEL_MAX_LENGTH = 100


class CashAccountMigrationError(RuntimeError):
    pass


def _fail_if_any(connection: sa.Connection, query: str, message: str) -> None:
    rows = connection.execute(sa.text(query)).all()
    if not rows:
        return

    details = "; ".join(" ".join(str(value) for value in row) for row in rows)
    raise CashAccountMigrationError(f"{message}: {details}")


def _check_currencies(connection: sa.Connection) -> None:
    _fail_if_any(
        connection,
        f"""
        SELECT cash_account_id, currency
        FROM cash_accounts
        WHERE currency NOT IN ({CURRENCY_LIST})
        ORDER BY cash_account_id
        """,
        f"cash accounts with a currency outside {', '.join(CURRENCIES)}",
    )


def _merge_clashing_labels(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            """
            CREATE TEMPORARY TABLE merged_cash_accounts ON COMMIT DROP AS
            SELECT cash_account_id
            FROM cash_accounts c
            WHERE EXISTS (
                SELECT 1
                FROM cash_accounts o
                WHERE o.from_user_id = c.from_user_id
                  AND o.label = c.label
                  AND o.cash_account_id <> c.cash_account_id
            )
            """
        )
    )

    _fail_if_any(
        connection,
        f"""
        SELECT c.cash_account_id, length(c.institution || ' ' || c.label)
        FROM cash_accounts c
        JOIN merged_cash_accounts m USING (cash_account_id)
        WHERE length(c.institution || ' ' || c.label) > {LABEL_MAX_LENGTH}
        ORDER BY c.cash_account_id
        """,
        f"merged labels longer than {LABEL_MAX_LENGTH} characters (account id, length)",
    )

    connection.execute(
        sa.text(
            """
            UPDATE cash_accounts c
            SET label = c.institution || ' ' || c.label
            FROM merged_cash_accounts m
            WHERE m.cash_account_id = c.cash_account_id
            """
        )
    )

    _fail_if_any(
        connection,
        """
        SELECT from_user_id, label, string_agg(cash_account_id::text, ',' ORDER BY cash_account_id)
        FROM cash_accounts
        GROUP BY from_user_id, label
        HAVING count(*) > 1
        ORDER BY from_user_id, label
        """,
        "labels that still clash after merging (user, label, account ids)",
    )


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    _check_currencies(connection)
    _merge_clashing_labels(connection)

    op.drop_constraint(
        op.f("ck_cash_accounts_interest_rate_range"), "cash_accounts", type_="check"
    )
    op.drop_constraint(
        op.f("ck_cash_accounts_currency_iso"), "cash_accounts", type_="check"
    )
    op.drop_constraint(
        op.f("uq_cash_accounts_from_user_id"), "cash_accounts", type_="unique"
    )

    op.drop_column("cash_accounts", "institution")
    op.drop_column("cash_accounts", "interest_rate")

    op.create_unique_constraint(
        op.f("uq_cash_accounts_from_user_id"),
        "cash_accounts",
        ["from_user_id", "label"],
    )
    op.create_check_constraint(
        op.f("ck_cash_accounts_currency_allowed"),
        "cash_accounts",
        f"currency IN ({CURRENCY_LIST})",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("ck_cash_accounts_currency_allowed"), "cash_accounts", type_="check"
    )
    op.drop_constraint(
        op.f("uq_cash_accounts_from_user_id"), "cash_accounts", type_="unique"
    )

    op.add_column(
        "cash_accounts",
        sa.Column(
            "institution",
            sa.String(length=100),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.alter_column("cash_accounts", "institution", server_default=None)
    op.add_column(
        "cash_accounts", sa.Column("interest_rate", sa.Numeric(), nullable=True)
    )

    op.create_unique_constraint(
        op.f("uq_cash_accounts_from_user_id"),
        "cash_accounts",
        ["from_user_id", "institution", "label"],
    )
    op.create_check_constraint(
        op.f("ck_cash_accounts_currency_iso"),
        "cash_accounts",
        "currency ~ '^[A-Z]{3}$'",
    )
    op.create_check_constraint(
        op.f("ck_cash_accounts_interest_rate_range"),
        "cash_accounts",
        "interest_rate >= 0 AND interest_rate <= 100",
    )
