"""initial schema

Cria as 9 tabelas da seção 11 do master prompt: assets, candles, playbooks,
opportunities, evidence, alerts, scanner_events, system_health, backtests.

Revision ID: 0001
Revises:
Create Date: 2026-08-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# create_type=False: os tipos ENUM são criados/removidos explicitamente em
# upgrade()/downgrade() (checkfirst=True), então create_table não deve
# tentar recriá-los.
opportunity_status = postgresql.ENUM(
    "FORMATION", "CONFIRMED", "INVALIDATED", "EXPIRED",
    name="opportunitystatus", create_type=False,
)
direction_enum = postgresql.ENUM("LONG", "SHORT", name="direction", create_type=False)
decision_result = postgresql.ENUM(
    "ENTRAR", "ESPERAR", "REPROVAR", name="decisionresult", create_type=False,
)
playbook_status = postgresql.ENUM(
    "ACTIVE", "VALIDATING", "EXPERIMENTAL", "SUSPENDED", "RETIRED",
    name="playbookstatus", create_type=False,
)
alert_type = postgresql.ENUM(
    "SIGNAL", "FUTURE", "INVALIDATION", name="alerttype", create_type=False,
)
telegram_status = postgresql.ENUM(
    "PENDING", "SENT", "FAILED", name="telegramstatus", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (
        opportunity_status, direction_enum, decision_result,
        playbook_status, alert_type, telegram_status,
    ):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("exchange", sa.String(32), nullable=False, server_default="BINANCE"),
        sa.Column("market", sa.String(16), nullable=False, server_default="SPOT"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_assets_symbol", "assets", ["symbol"], unique=True)

    op.create_table(
        "candles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(18, 8), nullable=False),
        sa.Column("high", sa.Numeric(18, 8), nullable=False),
        sa.Column("low", sa.Numeric(18, 8), nullable=False),
        sa.Column("close", sa.Numeric(18, 8), nullable=False),
        sa.Column("volume", sa.Numeric(24, 8), nullable=False),
        sa.UniqueConstraint("asset_id", "timeframe", "timestamp", name="uq_candle_key"),
    )
    op.create_index("ix_candles_asset_id", "candles", ["asset_id"])
    op.create_index("ix_candles_timestamp", "candles", ["timestamp"])

    op.create_table(
        "playbooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("version", sa.String(16), nullable=False, server_default="v1.0"),
        sa.Column("tier", sa.String(8), nullable=False, server_default="A"),
        sa.Column("minimum_score", sa.Float(), nullable=False, server_default="70.0"),
        sa.Column("minimum_rr", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("status", playbook_status, nullable=False, server_default="EXPERIMENTAL"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_playbooks_name", "playbooks", ["name"], unique=True)

    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset", sa.String(32), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("playbook", sa.String(64), nullable=False),
        sa.Column("direction", direction_enum, nullable=False),
        sa.Column("status", opportunity_status, nullable=False, server_default="FORMATION"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="BAIXA"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("entry", sa.Numeric(18, 8), nullable=True),
        sa.Column("stop", sa.Numeric(18, 8), nullable=True),
        sa.Column("tp1", sa.Numeric(18, 8), nullable=True),
        sa.Column("tp2", sa.Numeric(18, 8), nullable=True),
        sa.Column("tp3", sa.Numeric(18, 8), nullable=True),
        sa.Column("rr", sa.Float(), nullable=True),
        sa.Column("decision", decision_result, nullable=True),
        sa.Column("playbook_version", sa.String(16), nullable=False, server_default="v1.0"),
        sa.Column("algorithm_version", sa.String(16), nullable=False, server_default="v1.0"),
        sa.Column("audit_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_opportunities_asset", "opportunities", ["asset"])
    op.create_index("ix_opportunities_playbook", "opportunities", ["playbook"])
    op.create_index("ix_opportunities_status", "opportunities", ["status"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("evidence", sa.String(512), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_evidence_opportunity_id", "evidence", ["opportunity_id"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("alert_type", alert_type, nullable=False),
        sa.Column("telegram_status", telegram_status, nullable=False, server_default="PENDING"),
        sa.Column("chat_id", sa.String(32), nullable=False),
        sa.Column("message_id", sa.String(32), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(512), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alerts_opportunity_id", "alerts", ["opportunity_id"])

    op.create_table(
        "scanner_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("asset", sa.String(32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "system_health",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="UNKNOWN"),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.String(512), nullable=True),
    )
    op.create_index("ix_system_health_service", "system_health", ["service"], unique=True)

    op.create_table(
        "backtests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("playbook", sa.String(64), nullable=False),
        sa.Column("asset", sa.String(32), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("payoff", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("profit_factor", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("expectancy", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("max_drawdown", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_backtests_playbook", "backtests", ["playbook"])


def downgrade() -> None:
    op.drop_table("backtests")
    op.drop_table("system_health")
    op.drop_table("scanner_events")
    op.drop_table("alerts")
    op.drop_table("evidence")
    op.drop_table("opportunities")
    op.drop_table("playbooks")
    op.drop_table("candles")
    op.drop_table("assets")

    bind = op.get_bind()
    for enum in (
        telegram_status, alert_type, playbook_status,
        decision_result, direction_enum, opportunity_status,
    ):
        enum.drop(bind, checkfirst=True)
