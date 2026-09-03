"""
persistence/models.py
========================

Modelos ORM:

- `SetupRecord` (Fase 2 -- Documento 2, seção 14).
- `AccountState`, `OpenPositionRecord`, `RiskEvent` (Fase 4 -- Risk Engine).
- `SignalRecord` (Fase 5 -- Learning Engine / Signal Feature Database:
  Documento 2, seção 30; Documento Master, seção 27, 30).

`playbooks` (stats persistidas), `backtests` salvos, `market_regimes`
etc. (Documento Master, seção 46) ficam para quando algo realmente os
usar -- criar a tabela antes disso só adicionaria uma migração vazia.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SetupRecord(Base):
    __tablename__ = "setups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # "long" | "short"
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(String(24), nullable=False)

    entry_zone_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_zone_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    trigger: Mapped[str | None] = mapped_column(String(256), nullable=True)
    stop: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp1: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp2: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp3: Mapped[float | None] = mapped_column(Float, nullable=True)
    rr: Mapped[float | None] = mapped_column(Float, nullable=True)

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: histórico de score ao longo da vida do setup (Documento 2, seção 15:
    #: "Score: 78 -> 83 -> 88") -- lista de {"timestamp": iso, "score": float}.
    score_history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    invalidation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reason_for_change: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Campos de execução real e performance (Strategy Engine V2)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)  # TP1, TP2, TP3, STOP, INVALIDATED, EXPIRED
    realized_pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_r_multiple: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_setups_lookup", "asset", "direction", "strategy", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "asset": self.asset,
            "direction": self.direction,
            "strategy": self.strategy,
            "status": self.status,
            "entry_zone": (
                {"low": self.entry_zone_low, "high": self.entry_zone_high}
                if self.entry_zone_low is not None or self.entry_zone_high is not None
                else None
            ),
            "trigger": self.trigger,
            "stop": self.stop,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "rr": self.rr,
            "score": self.score,
            "score_history": self.score_history,
            "invalidation": self.invalidation,
            "expiration": self.expiration.isoformat() if self.expiration else None,
            "reason_for_change": self.reason_for_change,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "realized_pnl_pct": self.realized_pnl_pct,
            "realized_r_multiple": self.realized_r_multiple,
            "regime": self.regime,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "duration_minutes": self.duration_minutes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status_changed_at": self.status_changed_at.isoformat(),
        }



class AccountState(Base):
    """
    Singleton por `account_id` (Fase 4 -- Risk Engine). Capital e
    limites de risco vivem juntos aqui porque ambos mudam raramente e
    são sempre lidos juntos (`risk/repository.py`) -- evita duas
    consultas onde uma resolve.
    """

    __tablename__ = "account_state"

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True, default="default")

    starting_capital: Mapped[float] = mapped_column(Float, nullable=False)
    current_capital: Mapped[float] = mapped_column(Float, nullable=False)

    #: limites configuráveis (Documento 2, seção 21) -- percentuais (ex.: 1.0 = 1%).
    max_risk_per_trade_pct: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    daily_loss_limit_pct: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    weekly_loss_limit_pct: Mapped[float] = mapped_column(Float, nullable=False, default=6.0)
    monthly_drawdown_limit_pct: Mapped[float] = mapped_column(Float, nullable=False, default=12.0)
    max_open_risk_pct: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "starting_capital": self.starting_capital,
            "current_capital": self.current_capital,
            "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "weekly_loss_limit_pct": self.weekly_loss_limit_pct,
            "monthly_drawdown_limit_pct": self.monthly_drawdown_limit_pct,
            "max_open_risk_pct": self.max_open_risk_pct,
            "updated_at": self.updated_at.isoformat(),
        }


class OpenPositionRecord(Base):
    """Posições abertas no momento -- soma de `risk_pct` = Open Risk (Documento Master, seção 21)."""

    __tablename__ = "open_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")

    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    risk_pct: Mapped[float] = mapped_column(Float, nullable=False)
    #: grupo de correlação (Fase 3, `discovery.correlation`) -- opcional,
    #: usado pelo Risk Engine para negar/reduzir uma segunda posição no
    #: mesmo cluster em vez de só emitir uma nota informativa.
    correlation_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    setup_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # referência informativa a SetupRecord.id

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (Index("ix_open_positions_account", "account_id"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "asset": self.asset,
            "direction": self.direction,
            "risk_pct": self.risk_pct,
            "correlation_group": self.correlation_group,
            "setup_id": self.setup_id,
            "opened_at": self.opened_at.isoformat(),
        }


class RiskEvent(Base):
    """Log de trades encerrados (realizados) -- base para os limites diário/semanal/mensal."""

    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")

    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    risk_pct: Mapped[float] = mapped_column(Float, nullable=False)
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=False)  # % do capital, positivo ou negativo

    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (Index("ix_risk_events_account_closed", "account_id", "closed_at"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "asset": self.asset,
            "direction": self.direction,
            "risk_pct": self.risk_pct,
            "pnl_pct": self.pnl_pct,
            "closed_at": self.closed_at.isoformat(),
        }


class SignalRecord(Base):
    """
    Sinal externo (call de terceiros) + contexto reconstruído no
    momento em que foi emitido (Documento 2, seção 30). `result`/
    `r_multiple` ficam `None` até o resultado ser conhecido -- um
    sinal registrado sem resultado ainda é útil (entra no Reverse
    Engineering), só não entra nas estatísticas de hipótese até ter
    resultado.
    """

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    signal_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    entry: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp1: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp2: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp3: Mapped[float | None] = mapped_column(Float, nullable=True)
    rr: Mapped[float | None] = mapped_column(Float, nullable=True)

    source: Mapped[str] = mapped_column(String(128), nullable=False)  # de onde veio o sinal (grupo/pessoa/canal)
    strategy_guess: Mapped[str | None] = mapped_column(String(64), nullable=True)  # estratégia implícita inferida

    #: contexto reconstruído no momento do sinal (regime, estrutura, bos/choch,
    #: quality/confirmation score) -- ver learning/reconstruction.py. JSON porque
    #: a composição exata do contexto pode evoluir sem exigir migração de schema.
    reconstructed_context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    result: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "win" | "loss" | "breakeven" | None
    r_multiple: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_quality: Mapped[str | None] = mapped_column(String(256), nullable=True)

    signal_quality_label: Mapped[str | None] = mapped_column(String(32), nullable=True)  # ver learning/classification.py

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (Index("ix_signals_asset_strategy", "asset", "strategy_guess"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "asset": self.asset,
            "direction": self.direction,
            "timeframe": self.timeframe,
            "signal_time": self.signal_time.isoformat(),
            "entry": self.entry,
            "stop": self.stop,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "rr": self.rr,
            "source": self.source,
            "strategy_guess": self.strategy_guess,
            "reconstructed_context": self.reconstructed_context,
            "result": self.result,
            "r_multiple": self.r_multiple,
            "execution_quality": self.execution_quality,
            "signal_quality_label": self.signal_quality_label,
            "created_at": self.created_at.isoformat(),
        }

class SystemCycle(Base):
    """Registro de cada ciclo autônomo do sistema."""
    __tablename__ = "system_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    universe_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage1_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage2_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discovery_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    playbook_valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    setups_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    setups_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    setups_expired: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    setups_invalidated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    errors_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "universe_size": self.universe_size,
            "stage1_count": self.stage1_count,
            "stage2_count": self.stage2_count,
            "discovery_count": self.discovery_count,
            "playbook_valid_count": self.playbook_valid_count,
            "quality_valid_count": self.quality_valid_count,
            "setups_created": self.setups_created,
            "setups_updated": self.setups_updated,
            "setups_expired": self.setups_expired,
            "setups_invalidated": self.setups_invalidated,
            "signals_sent": self.signals_sent,
            "errors_count": self.errors_count,
            "error_summary": self.error_summary,
            "status": self.status,
        }

class TelegramSignal(Base):
    """Registro de calls enviadas ao Telegram para deduplicação."""
    __tablename__ = "telegram_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    setup_id: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message_text: Mapped[str] = mapped_column(String, nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    __table_args__ = (Index("ix_telegram_signals_setup_type", "setup_id", "signal_type"),)

class CandidateSnapshot(Base):
    """Snapshot minimizado de candidatos rejeitados/analisados por ciclo (para dashboard/auditoria)."""
    __tablename__ = "candidate_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    
    __table_args__ = (Index("ix_candidate_snapshots_cycle", "cycle_id"),)
