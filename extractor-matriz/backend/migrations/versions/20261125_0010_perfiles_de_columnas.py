"""perfiles de columnas de la pestaña Buscar (ADR 0011, Fase 2)

Revisión: 0010
Anterior: '0009'
Fecha: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')


def upgrade() -> None:
    op.create_table(
        'descubrimiento_perfiles',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('proyecto_id', sa.Uuid(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('columnas', JSONB, nullable=False),
        sa.Column('predeterminado', sa.Boolean(), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['proyecto_id'], ['proyectos.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('proyecto_id', 'nombre', name='uq_perfil_nombre'),
    )
    with op.batch_alter_table('descubrimiento_perfiles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_descubrimiento_perfiles_proyecto_id'), ['proyecto_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('descubrimiento_perfiles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_descubrimiento_perfiles_proyecto_id'))
    op.drop_table('descubrimiento_perfiles')
