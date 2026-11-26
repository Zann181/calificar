"""dónde se lanzó cada búsqueda: en el equipo o en la web, aún sin recoger (ADR 0012)

Revisión: 0012
Anterior: '0011'
Fecha: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('descubrimiento_busquedas',
                  sa.Column('origen', sa.String(length=10), server_default='equipo', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('descubrimiento_busquedas') as tabla:
        tabla.drop_column('origen')
