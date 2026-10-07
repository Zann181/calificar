"""avance de extraccion

Revisión: 0003
Anterior: '0002'
Fecha: 2026-10-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('extraccion_extracciones', schema=None) as batch_op:
        batch_op.add_column(sa.Column('progreso', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('paso', sa.String(length=20), server_default='preparando', nullable=False))
        batch_op.add_column(sa.Column('paso_desde', sa.DateTime(timezone=True), nullable=True))
    # Las extracciones ya completadas quedan al 100 %.
    op.execute("UPDATE extraccion_extracciones SET progreso = 100, paso = 'completada' WHERE estado = 'COMPLETADA'")


def downgrade() -> None:
    with op.batch_alter_table('extraccion_extracciones', schema=None) as batch_op:
        batch_op.drop_column('paso_desde')
        batch_op.drop_column('paso')
        batch_op.drop_column('progreso')
