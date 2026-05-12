"""rename group_type to role

Revision ID: 62810ee19208
Revises: a3f9c12e8b01
Create Date: 2026-05-12 16:18:16.134250

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "62810ee19208"
down_revision: Union[str, Sequence[str], None] = "a3f9c12e8b01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table("group_role_association", "group_member_role_association")
    op.rename_table("group_type_role_association", "group_role_association")


def downgrade() -> None:
    """Downgrade schema."""
    op.rename_table("group_role_association", "group_type_role_association")
    op.rename_table("group_member_role_association", "group_role_association")
