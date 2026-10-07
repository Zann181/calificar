"""datos del equipo en cada extraccion

Revisión: 0005
Anterior: '0004'
Fecha: 2026-10-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('extraccion_extracciones', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'datos_del_equipo', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            server_default='{}', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('extraccion_extracciones', schema=None) as batch_op:
        batch_op.drop_column('datos_del_equipo')
