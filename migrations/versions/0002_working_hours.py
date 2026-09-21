"""working_hours table

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-21

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "working_hours",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "practitioner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("practitioners.id"),
            nullable=False,
        ),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("day_of_week BETWEEN 0 AND 6", name="working_hours_day_of_week_range"),
        sa.CheckConstraint("start_time < end_time", name="working_hours_start_before_end"),
    )
    op.create_index(
        "ix_working_hours_practitioner_id", "working_hours", ["practitioner_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_working_hours_practitioner_id", table_name="working_hours")
    op.drop_table("working_hours")
