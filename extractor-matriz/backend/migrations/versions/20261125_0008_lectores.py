"""lectores de la nube agregados desde el panel local (ADR 0009, Fase 2)

Revisión: 0008
Anterior: '0007'
Fecha: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'sync_lectores',
        sa.Column('correo', sa.String(length=200), nullable=False),
        sa.Column('agregado_en', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('correo'),
    )


def downgrade() -> None:
    op.drop_table('sync_lectores')
