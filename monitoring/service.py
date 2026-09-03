"""
monitoring/service.py
========================

I/O do monitoramento (Documento Master, seção 34, 43-44): busca o
preço atual de cada ativo com setup em aberto e aplica as transições
que `setup_monitor.evaluate_setup_update` indicar, além da varredura
de expiração já existente (Fase 2). Ponto de entrada tanto do endpoint
`POST /monitoring/run-cycle` quanto do script de cron
(`scripts/run_monitoring_cycle.py`).

Mesma convenção de `discovery/engine.py` e `learning/reconstruction.py`:
função de integração com rede, não coberta por teste de unidade além
de um smoke test com provider fake -- a lógica pura já está em
`monitoring/setup_monitor.py`, testada à parte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from api.market_data import MarketData
from persistence.models import SetupRecord
from setups.expiration import sweep_expired
from setups.lifecycle import validate_transition
from setups.repository import list_setups
from monitoring.setup_monitor import SetupSnapshot, evaluate_setup_update


@dataclass(frozen=True, slots=True)
class MonitoringCycleResult:
    checked: int
    updated: list[dict] = field(default_factory=list)
    expired: list[int] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"checked": self.checked, "updated": self.updated, "expired": self.expired, "errors": self.errors}


def _to_snapshot(record: SetupRecord) -> SetupSnapshot:
    return SetupSnapshot(
        status=record.status,
        direction=record.direction,
        entry_zone_low=record.entry_zone_low,
        entry_zone_high=record.entry_zone_high,
        stop=record.stop,
        tp1=record.tp1,
        tp2=record.tp2,
        tp3=record.tp3,
    )


def run_monitoring_cycle(session: Session, market_data: MarketData | None = None, now: datetime | None = None) -> MonitoringCycleResult:
    """
    Ordem: expira primeiro (não faz sentido buscar preço de um setup
    que já devia ter expirado), depois checa preço dos que sobraram.
    """
    now = now or datetime.now(timezone.utc)
    md = market_data or MarketData()

    expired_ids = sweep_expired(session, now=now)

    open_setups = list_setups(session, exclude_terminal=True)
    updated: list[dict] = []
    errors: dict[str, str] = {}

    for record in open_setups:
        try:
            quote = md.get_current_price(symbol=record.asset)
        except Exception as exc:  # noqa: BLE001 - preço indisponível para 1 ativo não deve travar o ciclo inteiro.
            errors[record.asset] = str(exc)
            continue

        update = evaluate_setup_update(quote, _to_snapshot(record))
        if update is None:
            continue

        try:
            validate_transition(record.status, update.new_status)
        except ValueError as exc:
            errors[f"{record.asset}#{record.id}"] = str(exc)
            continue

        previous_status = record.status
        record.status = update.new_status
        record.status_changed_at = now
        record.reason_for_change = update.reason

        # Inicializar abertura do trade e status de execução
        if not record.entry_price and record.status in ("NEAR_ENTRY", "READY", "TRIGGERED", "ACTIVE"):
            record.entry_price = quote
            record.opened_at = now
            if record.signal_sent_at and not record.trade_opened_at:
                record.trade_opened_at = now
                record.signal_status = "ACTIVE"

        # Calcular encerramento e resultado financeiro real
        if update.new_status in ("COMPLETED", "INVALIDATED", "TP1", "TP2", "TP3"):
            entry_p = record.entry_price or record.entry_zone_low or quote
            record.exit_price = quote
            
            risk_dist = abs(entry_p - record.stop) if (record.stop and entry_p) else (0.01 * entry_p)
            if record.direction == "long":
                pnl = (quote - entry_p) / entry_p * 100 if entry_p else 0.0
                r_mult = (quote - entry_p) / risk_dist if risk_dist else 0.0
            else:
                pnl = (entry_p - quote) / entry_p * 100 if entry_p else 0.0
                r_mult = (entry_p - quote) / risk_dist if risk_dist else 0.0

            record.realized_pnl_pct = pnl
            record.realized_r_multiple = r_mult

            if update.new_status in ("COMPLETED", "INVALIDATED"):
                record.closed_at = now
                record.exit_reason = "STOP" if update.new_status == "INVALIDATED" else "TP"
                if record.opened_at:
                    record.duration_minutes = (now - record.opened_at).total_seconds() / 60.0
                
                if record.signal_sent_at:
                    record.signal_status = "STOP_HIT" if update.new_status == "INVALIDATED" else "CLOSED"
            elif record.signal_sent_at:
                record.signal_status = f"{update.new_status}_HIT"

        updated.append({"setup_id": record.id, "asset": record.asset, "from": previous_status, "to": update.new_status, "reason": update.reason})

    session.flush()
    return MonitoringCycleResult(checked=len(open_setups), updated=updated, expired=expired_ids, errors=errors)
