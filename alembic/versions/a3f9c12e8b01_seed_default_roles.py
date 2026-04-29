"""seed default roles

Revision ID: a3f9c12e8b01
Revises: e8b27dd51414
Create Date: 2026-04-28 00:00:00.000000

"""
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "a3f9c12e8b01"
down_revision: Union[str, Sequence[str], None] = "e8b27dd51414"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_ROLES = [
    "teacher",
    "student",
    "legal_guardian",
    "legal_ward",
    "school_class",
    "workgroup",
    "staff",
    "school",
]


def upgrade() -> None:
    role_table = sa.table(
        "role",
        sa.column("public_id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("display_name", sa.JSON()),
    )
    op.bulk_insert(
        role_table,
        [{"public_id": str(uuid4()), "name": name, "display_name": {}} for name in _DEFAULT_ROLES],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM role WHERE name = ANY(:names)").bindparams(names=_DEFAULT_ROLES))
