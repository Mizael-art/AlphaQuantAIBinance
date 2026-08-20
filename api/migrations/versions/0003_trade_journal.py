"""trade journal

Cria as tabelas `trades` e `trade_events` (seções 77-106 — Signal/Trade
Journal): acompanhamento hipotético de cada sinal CONFIRMED, com
lifecycle multi-TP, PnL/R e trilha de eventos para auditoria.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


direction_enum = postgresql.ENUM("LONG", "SHORT", name="direction", create_type=False)
trade_status = postgresql.ENUM(
    "OPEN", "TP1_HIT", "TP2_HIT", "TP3_HIT", "TP4_HIT", "TP5_HIT",
    "STOP_HIT", "CLOSED", "EXPIRED", "INVALIDATED",
    name="tradestatus", create_type=False,
)
trade_result = postgresql.ENUM(
    "WIN", "LOSS", "BREAKEVEN", "PARTIAL_WIN", "PARTIAL_LOSS",
    name="traderesult", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (trade_status, trade_result):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("asset", sa.String(32), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("direction", direction_enum, nullable=False),
        sa.Column("strategy_name", sa.String(64), nullable=False),
        sa.Column("strategy_version", sa.String(16), nullable=False, server_default="v1.0"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("entry", sa.Numeric(18, 8), nullable=False),
        sa.Column("initial_stop", sa.Numeric(18, 8), nullable=False),
        sa.Column("stop", sa.Numeric(18, 8), nullable=False),
        sa.Column("targets", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("move_to_breakeven_after_tp1", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", trade_status, nullable=False, server_default="OPEN"),
        sa.Column("result", trade_result, nullable=True),
        sa.Column("remaining_pct", sa.Float(), nullable=False, server_default="100.0"),
        sa.Column("realized_pnl_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("realized_r", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("last_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("last_price_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trades_opportunity_id", "trades", ["opportunity_id"])
    op.create_index("ix_trades_asset", "trades", ["asset"])
    op.create_index("ix_trades_strategy_name", "trades", ["strategy_name"])
    op.create_index("ix_trades_status", "trades", ["status"])

    op.create_table(
        "trade_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("trade_id", sa.Integer(), sa.ForeignKey("trades.id"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_trade_events_trade_id", "trade_events", ["trade_id"])
    op.create_index("ix_trade_events_timestamp", "trade_events", ["timestamp"])


def downgrade() -> None:
    op.drop_table("trade_events")
    op.drop_table("trades")

    bind = op.get_bind()
    for enum in (trade_result, trade_status):
        enum.drop(bind, checkfirst=True)
