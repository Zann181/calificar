"""sincronización con la nube: destinos, corridas y estado de la nube (ADR 0009)

Revisión: 0007
Anterior: '0006'
Fecha: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')


def upgrade() -> None:
    op.create_table(
        'sync_destinos',
        sa.Column('proyecto_id', sa.Uuid(), nullable=False),
        sa.Column('url', sa.String(length=500), server_default='', nullable=False),
        sa.Column('automatico', sa.Boolean(), nullable=False),
        sa.Column('pausado', sa.Boolean(), nullable=False),
        sa.Column('agrupar_s', sa.Integer(), nullable=False),
        sa.Column('reconciliar_s', sa.Integer(), nullable=False),
        sa.Column('opciones', JSONB, nullable=False),
        sa.Column('instalacion_id', sa.String(length=40), nullable=False),
        sa.Column('sede', sa.String(length=10), server_default='local', nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['proyecto_id'], ['proyectos.id']),
        sa.PrimaryKeyConstraint('proyecto_id'),
    )
    op.create_table(
        'sync_corridas',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('proyecto_id', sa.Uuid(), nullable=False),
        sa.Column('iniciada_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('terminada_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('motivo', sa.String(length=20), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('sobres', sa.Integer(), nullable=False),
        sa.Column('eliminados', sa.Integer(), nullable=False),
        sa.Column('archivos', sa.Integer(), nullable=False),
        sa.Column('bytes_enviados', sa.Integer(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=True),
        sa.Column('detalle', sa.Text(), server_default='', nullable=False),
        sa.ForeignKeyConstraint(['proyecto_id'], ['proyectos.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('sync_corridas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sync_corridas_proyecto_id'), ['proyecto_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sync_corridas_iniciada_en'), ['iniciada_en'], unique=False)
    op.create_table(
        'sync_estado_nube',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('instalacion_id', sa.String(length=40), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('sync_estado_nube')
    with op.batch_alter_table('sync_corridas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sync_corridas_iniciada_en'))
        batch_op.drop_index(batch_op.f('ix_sync_corridas_proyecto_id'))
    op.drop_table('sync_corridas')
    op.drop_table('sync_destinos')
