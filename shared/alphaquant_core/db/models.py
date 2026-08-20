"""
Schema do banco de dados do AlphaQuant X.

Tabelas: assets, candles, opportunities, evidence, playbooks, alerts,
scanner_events, system_health, backtests.

Nenhum dado de mercado ou sinal é fabricado por este schema — ele apenas
armazena o que o Scanner/Worker efetivamente calcular.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alphaquant_core.db.session import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OpportunityStatus(str, enum.Enum):
    FORMATION = "FORMATION"      # future opportunity, em formação
    CONFIRMED = "CONFIRMED"      # sinal confirmado, enviado como SIGNAL
    INVALIDATED = "INVALIDATED"  # perdeu as condições
    EXPIRED = "EXPIRED"          # não confirmou a tempo


class Direction(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class DecisionResult(str, enum.Enum):
    ENTRAR = "ENTRAR"
    ESPERAR = "ESPERAR"
    REPROVAR = "REPROVAR"


class PlaybookStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    VALIDATING = "VALIDATING"
    EXPERIMENTAL = "EXPERIMENTAL"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class AlertType(str, enum.Enum):
    SIGNAL = "SIGNAL"
    FUTURE = "FUTURE"
    INVALIDATION = "INVALIDATION"


class StrategyStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class Strategy(Base):
    """
    Estratégia criada por PROMPT (seções 12-29). Persistida — sobrevive a
    restart do Worker/API (mesma exigência da seção 102 aplicada aqui).
    O texto do prompt e a validação ficam em `StrategyVersion`; esta
    tabela guarda só o que é estável entre versões (nome, modo, status).
    """
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="SCANNER")  # SCANNER | SWING | INTRADAY | DAY_TRADE
    status: Mapped[StrategyStatus] = mapped_column(Enum(StrategyStatus), default=StrategyStatus.ACTIVE, index=True)
    current_version_id: Mapped[int | None] = mapped_column(ForeignKey("strategy_versions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    versions: Mapped[list["StrategyVersion"]] = relationship(
        back_populates="strategy", order_by="StrategyVersion.id",
        foreign_keys="StrategyVersion.strategy_id",
    )
    current_version: Mapped["StrategyVersion | None"] = relationship(foreign_keys=[current_version_id])


class StrategyVersion(Base):
    """
    Uma versão imutável do prompt de uma estratégia (seção 28 — nunca
    sobrescrita; `update()` sempre cria uma linha nova e move
    `Strategy.current_version_id`).
    """
    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    version_label: Mapped[str] = mapped_column(String(16))  # "v1", "v2", ...
    prompt_raw: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(32))  # VALID | INVALID | UNSUPPORTED_CONDITION
    errors: Mapped[list] = mapped_column(JSON, default=list)
    unsupported_conditions: Mapped[list] = mapped_column(JSON, default=list)
    author: Mapped[str | None] = mapped_column(String(64), nullable=True)
    change_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    strategy: Mapped["Strategy"] = relationship(back_populates="versions", foreign_keys=[strategy_id])


class TelegramStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class TradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    TP1_HIT = "TP1_HIT"
    TP2_HIT = "TP2_HIT"
    TP3_HIT = "TP3_HIT"
    TP4_HIT = "TP4_HIT"
    TP5_HIT = "TP5_HIT"
    STOP_HIT = "STOP_HIT"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class TradeResult(str, enum.Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    PARTIAL_WIN = "PARTIAL_WIN"
    PARTIAL_LOSS = "PARTIAL_LOSS"


# ---------------------------------------------------------------------------
# Tabelas
# ---------------------------------------------------------------------------

class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    exchange: Mapped[str] = mapped_column(String(32), default="BINANCE")
    market: Mapped[str] = mapped_column(String(16), default="SPOT")  # SPOT | FUTURES
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    candles: Mapped[list["Candle"]] = relationship(back_populates="asset")


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("asset_id", "timeframe", "timestamp", name="uq_candle_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    timeframe: Mapped[str] = mapped_column(String(8))  # 15m, 1h, 4h, 1d ...
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Numeric(18, 8))
    high: Mapped[float] = mapped_column(Numeric(18, 8))
    low: Mapped[float] = mapped_column(Numeric(18, 8))
    close: Mapped[float] = mapped_column(Numeric(18, 8))
    volume: Mapped[float] = mapped_column(Numeric(24, 8))

    asset: Mapped["Asset"] = relationship(back_populates="candles")


class Playbook(Base):
    __tablename__ = "playbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    version: Mapped[str] = mapped_column(String(16), default="v1.0")
    tier: Mapped[str] = mapped_column(String(8), default="A")
    minimum_score: Mapped[float] = mapped_column(Float, default=70.0)
    minimum_rr: Mapped[float] = mapped_column(Float, default=2.0)
    status: Mapped[PlaybookStatus] = mapped_column(
        Enum(PlaybookStatus), default=PlaybookStatus.EXPERIMENTAL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8))
    playbook: Mapped[str] = mapped_column(String(64), index=True)
    direction: Mapped[Direction] = mapped_column(Enum(Direction))
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(OpportunityStatus), default=OpportunityStatus.FORMATION, index=True
    )

    # Os três números do Future Opportunity Engine são independentes entre si
    score: Mapped[float] = mapped_column(Float, default=0.0)         # qualidade da evidência (0-100 +5 bônus)
    confidence: Mapped[str] = mapped_column(String(16), default="BAIXA")  # BAIXA | MODERADA | ALTA
    progress: Mapped[float] = mapped_column(Float, default=0.0)      # % de condições do playbook atendidas

    entry: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    stop: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    tp1: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    tp2: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    tp3: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    rr: Mapped[float | None] = mapped_column(Float, nullable=True)

    decision: Mapped[DecisionResult | None] = mapped_column(Enum(DecisionResult), nullable=True)

    # Auditoria — seção 57: toda oportunidade deve ser reproduzível
    playbook_version: Mapped[str] = mapped_column(String(16), default="v1.0")
    algorithm_version: Mapped[str] = mapped_column(String(16), default="v1.0")
    audit_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="opportunity")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="opportunity")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    category: Mapped[str] = mapped_column(String(32))  # context | structure | liquidity | volume | smc | wyckoff
    evidence: Mapped[str] = mapped_column(String(512))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    opportunity: Mapped["Opportunity"] = relationship(back_populates="evidence")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType))
    telegram_status: Mapped[TelegramStatus] = mapped_column(Enum(TelegramStatus), default=TelegramStatus.PENDING)
    chat_id: Mapped[str] = mapped_column(String(32))
    message_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    opportunity: Mapped["Opportunity"] = relationship(back_populates="alerts")


class ScannerEvent(Base):
    __tablename__ = "scanner_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    asset: Mapped[str] = mapped_column(String(32))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class SystemHealth(Base):
    __tablename__ = "system_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service: Mapped[str] = mapped_column(String(32), unique=True)  # worker | api | database | telegram | data_feed
    status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")  # ONLINE | OFFLINE | DEGRADED
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)


class ManualScanRequest(Base):
    """
    Fila de pedidos de análise manual disparados pelo comando /analisar
    no Telegram (webhook `POST /webhooks/telegram`). O Worker (ou o
    scanner embutido da API no Free Plan) faz polling curto desta tabela
    enquanto espera o próximo fechamento de vela automático, e roda um
    ciclo de scan assim que encontra um pedido `processed_at IS NULL` —
    sem esperar os 15 minutos do ciclo agendado.
    """
    __tablename__ = "manual_scan_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requested_by_chat_id: Mapped[str] = mapped_column(String(32))
    requested_by_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Backtest(Base):
    __tablename__ = "backtests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playbook: Mapped[str] = mapped_column(String(64), index=True)
    asset: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    payoff: Mapped[float] = mapped_column(Float, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    expectancy: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Trade(Base):
    """
    Acompanhamento de uma operação hipotética nascida de um sinal
    CONFIRMED (seções 77-106). NUNCA representa execução real — ver
    `alphaquant_core.engines.trade_engine` para a lógica pura de
    lifecycle/PnL/R que esta tabela persiste.

    Separação SIGNAL vs TRADE (seção 96): `opportunity_id` é o SIGNAL
    que originou esta TRADE; a Opportunity nunca é sobrescrita por
    dados de acompanhamento de preço.
    """
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)

    asset: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8))
    direction: Mapped[Direction] = mapped_column(Enum(Direction))
    strategy_name: Mapped[str] = mapped_column(String(64), index=True)
    strategy_version: Mapped[str] = mapped_column(String(16), default="v1.0")
    score: Mapped[float] = mapped_column(Float, default=0.0)

    entry: Mapped[float] = mapped_column(Numeric(18, 8))
    initial_stop: Mapped[float] = mapped_column(Numeric(18, 8))
    stop: Mapped[float] = mapped_column(Numeric(18, 8))  # pode mover para breakeven (seção 90)
    targets: Mapped[list] = mapped_column(JSON, default=list)  # [{price, exit_pct, rr, hit, hit_at, hit_price}]
    move_to_breakeven_after_tp1: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[TradeStatus] = mapped_column(Enum(TradeStatus), default=TradeStatus.OPEN, index=True)
    result: Mapped[TradeResult | None] = mapped_column(Enum(TradeResult), nullable=True)
    remaining_pct: Mapped[float] = mapped_column(Float, default=100.0)
    realized_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    realized_r: Mapped[float] = mapped_column(Float, default=0.0)

    last_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    last_price_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Seção 85 — snapshot do MarketContext no instante do sinal, para
    # responder "o que o AlphaQuant estava vendo quando gerou esse sinal?"
    # sem depender dos dados atuais (que já mudaram).
    context_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    opportunity: Mapped["Opportunity"] = relationship()
    events: Mapped[list["TradeEvent"]] = relationship(back_populates="trade", order_by="TradeEvent.id")


class TradeEvent(Base):
    """Trilha de auditoria de UMA trade (seção 87): TRADE_CREATED,
    PRICE_UPDATE, TP1_HIT, STOP_HIT, INVALIDATED, CLOSED, etc."""
    __tablename__ = "trade_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    price: Mapped[float] = mapped_column(Numeric(18, 8))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    trade: Mapped["Trade"] = relationship(back_populates="events")
