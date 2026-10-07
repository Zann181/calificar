"""cola de extracciones

Revisión: 0004
Anterior: '0003'
Fecha: 2026-10-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'extraccion_cola',
        sa.Column('articulo_id', sa.Uuid(), nullable=False),
        sa.Column('proyecto_id', sa.Uuid(), nullable=False),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.Column('opciones', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
                  nullable=False),
        sa.Column('encolado_en', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['proyecto_id'], ['proyectos.id']),
        sa.PrimaryKeyConstraint('articulo_id'),
    )
    with op.batch_alter_table('extraccion_cola', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_extraccion_cola_proyecto_id'), ['proyecto_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('extraccion_cola', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_extraccion_cola_proyecto_id'))
    op.drop_table('extraccion_cola')
