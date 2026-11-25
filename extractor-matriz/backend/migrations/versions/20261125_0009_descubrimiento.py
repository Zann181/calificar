"""descubrimiento de literatura: búsquedas, candidatos y hallazgos (ADR 0011)

Revisión: 0009
Anterior: '0008'
Fecha: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')


def upgrade() -> None:
    op.create_table(
        'descubrimiento_busquedas',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('proyecto_id', sa.Uuid(), nullable=False),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('consulta', JSONB, nullable=False),
        sa.Column('fuentes', JSONB, nullable=False),
        sa.Column('limite_por_fuente', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(length=30), nullable=False),
        sa.Column('progreso', JSONB, nullable=False),
        sa.Column('total_unicos', sa.Integer(), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('terminada_en', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['proyecto_id'], ['proyectos.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('descubrimiento_busquedas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_descubrimiento_busquedas_proyecto_id'), ['proyecto_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_descubrimiento_busquedas_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_descubrimiento_busquedas_creado_en'), ['creado_en'], unique=False)

    op.create_table(
        'descubrimiento_candidatos',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('proyecto_id', sa.Uuid(), nullable=False),
        sa.Column('clave', sa.String(length=400), nullable=False),
        sa.Column('doi', sa.String(length=300), nullable=True),
        sa.Column('titulo', sa.Text(), nullable=False),
        sa.Column('anio', sa.Integer(), nullable=True),
        sa.Column('autores', JSONB, nullable=False),
        sa.Column('revista', sa.String(length=300), server_default='', nullable=False),
        sa.Column('resumen', sa.Text(), server_default='', nullable=False),
        sa.Column('palabras_clave', JSONB, nullable=False),
        sa.Column('idioma', sa.String(length=10), server_default='', nullable=False),
        sa.Column('tipo', sa.String(length=30), server_default='article', nullable=False),
        sa.Column('url_oa', sa.String(length=1000), nullable=True),
        sa.Column('es_preprint', sa.Boolean(), nullable=False),
        sa.Column('fuentes', JSONB, nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('motivo', sa.String(length=500), nullable=True),
        sa.Column('en_matriz', sa.Boolean(), nullable=False),
        sa.Column('articulo_id', sa.Uuid(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['proyecto_id'], ['proyectos.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('proyecto_id', 'clave', name='uq_candidato_clave'),
    )
    with op.batch_alter_table('descubrimiento_candidatos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_descubrimiento_candidatos_proyecto_id'), ['proyecto_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_descubrimiento_candidatos_doi'), ['doi'], unique=False)
        batch_op.create_index(batch_op.f('ix_descubrimiento_candidatos_anio'), ['anio'], unique=False)
        batch_op.create_index(batch_op.f('ix_descubrimiento_candidatos_estado'), ['estado'], unique=False)

    op.create_table(
        'descubrimiento_hallazgos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('busqueda_id', sa.Uuid(), nullable=False),
        sa.Column('candidato_id', sa.Uuid(), nullable=False),
        sa.Column('fuente', sa.String(length=40), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('visto_en', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['busqueda_id'], ['descubrimiento_busquedas.id']),
        sa.ForeignKeyConstraint(['candidato_id'], ['descubrimiento_candidatos.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('busqueda_id', 'candidato_id', 'fuente', name='uq_hallazgo'),
    )
    with op.batch_alter_table('descubrimiento_hallazgos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_descubrimiento_hallazgos_busqueda_id'), ['busqueda_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_descubrimiento_hallazgos_candidato_id'), ['candidato_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('descubrimiento_hallazgos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_descubrimiento_hallazgos_candidato_id'))
        batch_op.drop_index(batch_op.f('ix_descubrimiento_hallazgos_busqueda_id'))
    op.drop_table('descubrimiento_hallazgos')
    with op.batch_alter_table('descubrimiento_candidatos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_descubrimiento_candidatos_estado'))
        batch_op.drop_index(batch_op.f('ix_descubrimiento_candidatos_anio'))
        batch_op.drop_index(batch_op.f('ix_descubrimiento_candidatos_doi'))
        batch_op.drop_index(batch_op.f('ix_descubrimiento_candidatos_proyecto_id'))
    op.drop_table('descubrimiento_candidatos')
    with op.batch_alter_table('descubrimiento_busquedas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_descubrimiento_busquedas_creado_en'))
        batch_op.drop_index(batch_op.f('ix_descubrimiento_busquedas_estado'))
        batch_op.drop_index(batch_op.f('ix_descubrimiento_busquedas_proyecto_id'))
    op.drop_table('descubrimiento_busquedas')
