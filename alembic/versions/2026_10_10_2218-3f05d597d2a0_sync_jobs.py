"""sync jobs

Revision ID: 3f05d597d2a0
Revises: 6b7a6f337fb3
Create Date: 2026-10-10 22:18:12.231998

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3f05d597d2a0"
down_revision: Union[str, Sequence[str], None] = "6b7a6f337fb3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "sync_jobs",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("from_user_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "BACKFILL",
                "REFRESH",
                name="kind",
                native_enum=False,
                create_constraint=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "SUCCEEDED",
                "FAILED",
                name="status",
                native_enum=False,
                create_constraint=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("inserted", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("skipped", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "kind IN ('BACKFILL', 'REFRESH')", name=op.f("ck_sync_jobs_kind")
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name=op.f("ck_sync_jobs_status"),
        ),
        sa.CheckConstraint(
            "start_date <= end_date", name=op.f("ck_sync_jobs_date_range")
        ),
        sa.ForeignKeyConstraint(
            ["from_broker_id"],
            ["brokers.broker_id"],
            name=op.f("fk_sync_jobs_from_broker_id_brokers"),
        ),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.user_id"],
            name=op.f("fk_sync_jobs_from_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_sync_jobs")),
    )
    op.create_index(
        op.f("ix_sync_jobs_from_user_id"), "sync_jobs", ["from_user_id"], unique=False
    )
    op.create_index(
        "uq_sync_jobs_active_broker",
        "sync_jobs",
        ["from_broker_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'RUNNING')"),
    )
    op.execute("ALTER TABLE sync_jobs ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_sync_jobs_active_broker", table_name="sync_jobs")
    op.drop_index(op.f("ix_sync_jobs_from_user_id"), table_name="sync_jobs")
    op.drop_table("sync_jobs")
