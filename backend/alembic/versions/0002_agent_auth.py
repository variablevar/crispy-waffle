"""agent auth: audit table

Adds the agent_audit table used for agent-API request auditing.
No existing tables are modified.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_audit",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumer", sa.String(length=80), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=40), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
    )
    op.create_index("ix_agent_audit_ts", "agent_audit", ["ts"])
    op.create_index("ix_agent_audit_consumer", "agent_audit", ["consumer"])
    op.create_index("ix_agent_audit_request_id", "agent_audit", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_audit_request_id", table_name="agent_audit")
    op.drop_index("ix_agent_audit_consumer", table_name="agent_audit")
    op.drop_index("ix_agent_audit_ts", table_name="agent_audit")
    op.drop_table("agent_audit")
