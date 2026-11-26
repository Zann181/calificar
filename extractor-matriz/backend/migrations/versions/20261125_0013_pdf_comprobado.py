"""enlace del PDF gratuito comprobado de cada candidato (ADR 0013)

Revisión: 0013
Anterior: '0012'
Fecha: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('descubrimiento_candidatos', sa.Column('url_pdf', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('descubrimiento_candidatos') as tabla:
        tabla.drop_column('url_pdf')
