"""manual scan requests (comando /analisar do Telegram)

Cria a tabela `manual_scan_requests`: fila usada pelo webhook do
Telegram (`POST /webhooks/telegram`) para pedir um ciclo de scan
imediato, fora do agendamento automático de SCAN_INTERVAL_MINUTES.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manual_scan_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requested_by_chat_id", sa.String(32), nullable=False),
        sa.Column("requested_by_username", sa.String(128), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_manual_scan_requests_pending", "manual_scan_requests", ["processed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_manual_scan_requests_pending", table_name="manual_scan_requests")
    op.drop_table("manual_scan_requests")
