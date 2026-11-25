"""archivos en la base (AlmacenEnBase, ADR 0009)

Revisión: 0006
Anterior: '0005'
Fecha: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'biblioteca_archivos',
        sa.Column('clave', sa.String(length=500), nullable=False),
        sa.Column('tipo', sa.String(length=100), nullable=False),
        sa.Column('tamano', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('datos', sa.LargeBinary(), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('clave'),
    )
    with op.batch_alter_table('biblioteca_archivos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_biblioteca_archivos_sha256'), ['sha256'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('biblioteca_archivos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_biblioteca_archivos_sha256'))
    op.drop_table('biblioteca_archivos')
