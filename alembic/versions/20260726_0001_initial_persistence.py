"""Bootstrap the scoped PostgreSQL profile.

Revision ID: 20260726_0001
Revises:
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260726_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VECTOR_EXTENSION_LOCK_ID = 558555704712643079


def upgrade() -> None:
    op.execute(f"SELECT pg_advisory_xact_lock({_VECTOR_EXTENSION_LOCK_ID})")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_extension AS extension
                JOIN pg_namespace AS namespace
                  ON namespace.oid = extension.extnamespace
                WHERE extension.extname = 'vector'
                  AND namespace.nspname = 'public'
            ) THEN
                RAISE EXCEPTION 'vector extension must be installed in public schema';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # The extension is database-scoped and shared by independently migrated namespaces.
    pass
