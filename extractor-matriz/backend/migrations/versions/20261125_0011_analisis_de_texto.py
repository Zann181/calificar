"""análisis del texto completo de los candidatos (ADR 0011, etapa B)

Revisión: 0011
Anterior: '0010'
Fecha: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')


def upgrade() -> None:
    op.create_table(
        'descubrimiento_analisis',
        sa.Column('candidato_id', sa.Uuid(), nullable=False),
        sa.Column('celdas', JSONB, nullable=False),
        sa.Column('intentadas', JSONB, nullable=False),
        sa.Column('paginas', sa.Integer(), nullable=False),
        sa.Column('caracteres', sa.Integer(), nullable=False),
        sa.Column('suficiente', sa.Boolean(), nullable=False),
        sa.Column('origen', sa.String(length=100), nullable=False),
        sa.Column('analizado_en', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['candidato_id'], ['descubrimiento_candidatos.id']),
        sa.PrimaryKeyConstraint('candidato_id'),
    )


def downgrade() -> None:
    op.drop_table('descubrimiento_analisis')
