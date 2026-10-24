"""initial schema

Creates all SkyBus tables from the SQLAlchemy metadata and converts the
time-series tables into TimescaleDB hypertables when the extension is
available (plain PostgreSQL keeps working without it).

Revision ID: 0001
Create Date: 2026-10-22
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

from app.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_HYPERTABLES = [
    ("candles", "time"),
    ("trade_aggs", "time"),
    ("book_snapshots", "time"),
    ("funding_history", "time"),
    ("open_interest_history", "time"),
    ("sentiment_measurements", "time"),
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)

    # TimescaleDB hypertables — best effort; skip silently on plain Postgres.
    try:
        bind.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        for table, column in _HYPERTABLES:
            bind.execute(
                text(
                    "SELECT create_hypertable(:table, :column, if_not_exists => TRUE)"
                ),
                {"table": table, "column": column},
            )
    except Exception:
        pass


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
