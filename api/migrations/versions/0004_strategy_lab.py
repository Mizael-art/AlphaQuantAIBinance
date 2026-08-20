"""strategy lab persistence

Cria as tabelas `strategies` e `strategy_versions` (seções 12-29):
estratégias criadas por PROMPT, com versionamento verdadeiro (nunca
sobrescreve um prompt em vigor) e status ACTIVE/INACTIVE/ARCHIVED.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


strategy_status = postgresql.ENUM(
    "ACTIVE", "INACTIVE", "ARCHIVED", name="strategystatus", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    strategy_status.create(bind, checkfirst=True)

    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        # FK para strategies é adicionada depois de strategies existir (evita ciclo de criação)
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(16), nullable=False),
        sa.Column("prompt_raw", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("errors", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("unsupported_conditions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("author", sa.String(64), nullable=True),
        sa.Column("change_note", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="SCANNER"),
        sa.Column("status", strategy_status, nullable=False, server_default="ACTIVE"),
        sa.Column("current_version_id", sa.Integer(), sa.ForeignKey("strategy_versions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_foreign_key(
        "fk_strategy_versions_strategy_id", "strategy_versions", "strategies",
        ["strategy_id"], ["id"],
    )
    op.create_index("ix_strategies_name", "strategies", ["name"])
    op.create_index("ix_strategies_status", "strategies", ["status"])
    op.create_index("ix_strategy_versions_strategy_id", "strategy_versions", ["strategy_id"])


def downgrade() -> None:
    op.drop_constraint("fk_strategy_versions_strategy_id", "strategy_versions", type_="foreignkey")
    op.drop_table("strategies")
    op.drop_table("strategy_versions")

    bind = op.get_bind()
    strategy_status.drop(bind, checkfirst=True)
