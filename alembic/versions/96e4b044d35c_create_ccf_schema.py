# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""create the schema for the Common Connector Framework

The Kelvin connector runs on the Common Connector Framework (CCF), which keeps
its own tables (``tasks``, ``old``, ``morgue``, ...) and migrates them itself.
They live in the schema ``ccf`` of the Kelvin DB, so they survive a rebuild of
the connector container and the Kelvin API can read the morgue later. The CCF
connects with ``search_path=ccf`` (see ``kelvin_connector.ccf_launcher``) and
creates its tables on start, but cannot create the schema itself.

Autogenerate only inspects the default schema, so it does not propose to drop
the CCF tables.

Revision ID: 96e4b044d35c
Revises: e3d39f016714
Create Date: 2026-11-06 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "96e4b044d35c"
down_revision: str | Sequence[str] | None = "e3d39f016714"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CCF_SCHEMA = "ccf"


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_context().dialect.name == "postgresql":
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {CCF_SCHEMA}")


def downgrade() -> None:
    """Downgrade schema.

    Drops the CCF's tables with the schema, including tasks it has already
    acknowledged to provisioning but not processed yet.
    """
    if op.get_context().dialect.name == "postgresql":
        op.execute(f"DROP SCHEMA IF EXISTS {CCF_SCHEMA} CASCADE")
