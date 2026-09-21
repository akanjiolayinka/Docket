"""initial schema: extensions, patients, practitioners, appointments

Revision ID: 0001
Revises:
Create Date: 2026-09-21

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        "CREATE TYPE appointment_status AS ENUM "
        "('pending', 'accepted', 'cancelled', 'completed')"
    )

    op.create_table(
        "patients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "practitioners",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("specialty", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "appointments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patients.id"),
            nullable=False,
        ),
        sa.Column(
            "practitioner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("practitioners.id"),
            nullable=False,
        ),
        sa.Column("time_range", postgresql.TSTZRANGE, nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "accepted",
                "cancelled",
                "completed",
                name="appointment_status",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # The actual double-booking guarantee: no two pending/accepted
    # appointments for the same practitioner may have overlapping
    # time_range, enforced by Postgres itself (not app code) via GiST.
    op.execute(
        """
        ALTER TABLE appointments
        ADD CONSTRAINT appointments_no_overlap_per_practitioner
        EXCLUDE USING gist (
            practitioner_id WITH =,
            time_range WITH &&
        )
        WHERE (status IN ('pending', 'accepted'))
        """
    )

    op.create_index(
        "ix_appointments_practitioner_id", "appointments", ["practitioner_id"]
    )
    op.create_index("ix_appointments_patient_id", "appointments", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_appointments_patient_id", table_name="appointments")
    op.drop_index("ix_appointments_practitioner_id", table_name="appointments")
    op.drop_table("appointments")
    op.drop_table("practitioners")
    op.drop_table("patients")
    op.execute("DROP TYPE appointment_status")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
