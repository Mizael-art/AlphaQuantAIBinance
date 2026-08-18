"""seed playbooks

Insere os 10 Playbooks oficiais (seção 23 da especificação) na tabela
playbooks. Open Range Breakout começa EXPERIMENTAL; os demais começam
VALIDATING (nenhum passou por backtest ainda — seção 55).

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-09
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PLAYBOOKS = [
    ("Trend Continuation EMA50", "VALIDATING"),
    ("Liquidity Sweep Reversal", "VALIDATING"),
    ("Order Block Reaction", "VALIDATING"),
    ("FVG Retracement", "VALIDATING"),
    ("Breakout + Retest", "VALIDATING"),
    ("Wyckoff Spring", "VALIDATING"),
    ("Wyckoff Upthrust", "VALIDATING"),
    ("HTF Continuation", "VALIDATING"),
    ("Compression Breakout", "VALIDATING"),
    ("Open Range Breakout", "EXPERIMENTAL"),
]

playbooks_table = sa.table(
    "playbooks",
    sa.column("name", sa.String),
    sa.column("version", sa.String),
    sa.column("tier", sa.String),
    sa.column("minimum_score", sa.Float),
    sa.column("minimum_rr", sa.Float),
    sa.column("status", sa.String),
)


def upgrade() -> None:
    op.bulk_insert(
        playbooks_table,
        [
            {
                "name": name,
                "version": "v1.0",
                "tier": "A",
                "minimum_score": 70.0,
                "minimum_rr": 2.0,
                "status": status,
            }
            for name, status in PLAYBOOKS
        ],
    )


def downgrade() -> None:
    conn = op.get_bind()
    names = [name for name, _ in PLAYBOOKS]
    conn.execute(
        playbooks_table.delete().where(playbooks_table.c.name.in_(names))
    )
