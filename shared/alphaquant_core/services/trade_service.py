"""
trade_service — persistência do Trade Journal (seções 77-106).

Ponte entre o motor puro `engines/trade_engine.py` (sem I/O) e o banco:
- `create_trade_from_signal`: SIGNAL confirmado (Opportunity com
  decision=ENTRAR) -> TRADE aberto (seção 101, fluxo completo).
- `apply_price_update`: reconstrói o TradeState em memória a partir da
  linha `Trade`, aplica UM tick de preço (sem lookahead), grava os
  eventos gerados em `trade_events` e escreve de volta os campos
  mutáveis (stop, status, remaining_pct, realized_r, ...).
- `invalidate_trade` / `expire_trade`: idem, para os outros dois jeitos
  de uma trade fechar que não são nem TP nem stop.
- `performance_summary`: agregação para o Dashboard/Strategy Lab
  (seções 82/91/98) — nunca calcula sobre trades ainda abertas.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from alphaquant_core.db.models import (
    Direction as DBDirection,
)
from alphaquant_core.db.models import (
    Opportunity,
    Trade,
    TradeEvent,
)
from alphaquant_core.db.models import TradeResult as DBTradeResult
from alphaquant_core.db.models import TradeStatus as DBTradeStatus
from alphaquant_core.engines.trade_engine import (
    ExitReason,
    TargetLeg,
    TradeState,
    open_trade,
)
from alphaquant_core.engines.trade_engine import TradeStatus as EngineTradeStatus

_TP_REASON_BY_INDEX = [ExitReason.TP1, ExitReason.TP2, ExitReason.TP3, ExitReason.TP4, ExitReason.TP5]

OPEN_STATUSES = (
    DBTradeStatus.OPEN, DBTradeStatus.TP1_HIT, DBTradeStatus.TP2_HIT,
    DBTradeStatus.TP3_HIT, DBTradeStatus.TP4_HIT, DBTradeStatus.TP5_HIT,
)
CLOSED_STATUSES = (
    DBTradeStatus.STOP_HIT, DBTradeStatus.CLOSED, DBTradeStatus.EXPIRED, DBTradeStatus.INVALIDATED,
)


def _split_exit_pct(n: int) -> list[float]:
    """
    Divide 100% entre `n` alvos quando a Opportunity não trouxe um
    percentual explícito por TP (hoje `opportunity.tp1/tp2/tp3` são só
    preços — seção 89 pede % configurável por estratégia; o
    PromptStrategy/Strategy Lab, quando ativos, vão poder sobrescrever
    isso por `TargetRule.exit_pct`, já suportado no motor). Sem essa
    informação, a divisão mais neutra e' igual entre os alvos.
    """
    if n <= 0:
        return []
    base = round(100.0 / n, 4)
    pcts = [base] * n
    pcts[-1] = round(100.0 - base * (n - 1), 4)  # ajusta arredondamento no último
    return pcts


def create_trade_from_signal(
    db: Session, opportunity: Opportunity, *, move_to_breakeven_after_tp1: bool = False,
) -> Trade | None:
    """
    Cria a Trade a partir de uma Opportunity CONFIRMED (decision=ENTRAR).
    Devolve None (não cria nada) se faltar entry/stop/ao menos um TP —
    nunca inventa esses valores (mesma regra do Quality Filter/seção 15).
    """
    if opportunity.decision is None or opportunity.decision.value != "ENTRAR":
        return None
    if opportunity.entry is None or opportunity.stop is None:
        return None

    tp_prices = [p for p in (opportunity.tp1, opportunity.tp2, opportunity.tp3) if p is not None]
    if not tp_prices:
        return None

    pcts = _split_exit_pct(len(tp_prices))
    engine_targets = [
        TargetLeg(price=float(p), exit_pct=pct, rr=None) for p, pct in zip(tp_prices, pcts)
    ]

    engine_state = open_trade(
        asset=opportunity.asset,
        direction=_to_engine_direction(opportunity.direction),
        strategy_name=opportunity.playbook,
        entry=float(opportunity.entry),
        stop=float(opportunity.stop),
        targets=engine_targets,
        move_to_breakeven_after_tp1=move_to_breakeven_after_tp1,
    )

    trade = Trade(
        opportunity_id=opportunity.id,
        asset=opportunity.asset,
        timeframe=opportunity.timeframe,
        direction=DBDirection(opportunity.direction.value),
        strategy_name=opportunity.playbook,
        strategy_version=opportunity.playbook_version,
        score=float(opportunity.score),
        entry=engine_state.entry,
        initial_stop=engine_state.initial_stop,
        stop=engine_state.stop,
        targets=_targets_to_json(engine_state),
        move_to_breakeven_after_tp1=move_to_breakeven_after_tp1,
        status=DBTradeStatus.OPEN,
        remaining_pct=100.0,
        # Seção 85 — snapshot do MarketContext no instante do sinal.
        context_snapshot=dict(opportunity.audit_snapshot or {}),
    )
    db.add(trade)
    db.flush()

    db.add(TradeEvent(
        trade_id=trade.id, event_type="TRADE_CREATED",
        price=engine_state.entry, timestamp=datetime.now(timezone.utc),
        event_metadata={"targets": trade.targets, "stop": trade.stop},
    ))
    db.commit()
    db.refresh(trade)
    return trade


def apply_price_update(db: Session, trade: Trade, price: float, timestamp: datetime | None = None) -> list[TradeEvent]:
    """Um tick de preço (seção 86, a cada 15 minutos) para uma trade
    aberta. Idempotente para trades já fechadas (nenhuma linha nova)."""
    if trade.status not in OPEN_STATUSES:
        return []

    state = _rehydrate(trade)
    events = state.update_price(price, timestamp)
    _writeback(db, trade, state, events)
    return _persist_events(db, trade, events)


def invalidate_trade(db: Session, trade: Trade, price: float, reason: str, timestamp: datetime | None = None) -> list[TradeEvent]:
    if trade.status not in OPEN_STATUSES:
        return []
    state = _rehydrate(trade)
    events = state.invalidate(price=price, reason=reason, timestamp=timestamp)
    _writeback(db, trade, state, events)
    return _persist_events(db, trade, events)


def expire_trade(db: Session, trade: Trade, price: float, timestamp: datetime | None = None) -> list[TradeEvent]:
    if trade.status not in OPEN_STATUSES:
        return []
    state = _rehydrate(trade)
    events = state.expire(price=price, timestamp=timestamp)
    _writeback(db, trade, state, events)
    return _persist_events(db, trade, events)


def list_open_trades(db: Session) -> list[Trade]:
    return db.query(Trade).filter(Trade.status.in_(OPEN_STATUSES)).order_by(Trade.opened_at.desc()).all()


def list_closed_trades(db: Session, *, asset: str | None = None, strategy_name: str | None = None) -> list[Trade]:
    q = db.query(Trade).filter(Trade.status.in_(CLOSED_STATUSES))
    if asset:
        q = q.filter(Trade.asset == asset.upper())
    if strategy_name:
        q = q.filter(Trade.strategy_name == strategy_name)
    return q.order_by(Trade.closed_at.desc()).all()


def performance_summary(db: Session, *, strategy_name: str | None = None, since: datetime | None = None) -> dict:
    """Seções 82/91/98 — nunca inclui trades abertas (resultado ainda
    não existe para elas; usar `unrealized` separadamente no Dashboard)."""
    q = db.query(Trade).filter(Trade.status.in_(CLOSED_STATUSES))
    if strategy_name:
        q = q.filter(Trade.strategy_name == strategy_name)
    if since:
        q = q.filter(Trade.closed_at >= since)
    closed = q.all()

    open_count = db.query(func.count(Trade.id)).filter(Trade.status.in_(OPEN_STATUSES)).scalar() or 0

    total = len(closed)
    if total == 0:
        return {
            "open_trades": open_count, "closed_trades": 0, "win_rate": 0.0,
            "average_r": 0.0, "total_r": 0.0, "best_trade_r": None, "worst_trade_r": None,
            "profit_factor": None,
        }

    wins = [t for t in closed if t.result in (DBTradeResult.WIN, DBTradeResult.PARTIAL_WIN)]
    losses = [t for t in closed if t.result in (DBTradeResult.LOSS, DBTradeResult.PARTIAL_LOSS)]
    total_r = sum(t.realized_r for t in closed)
    gross_win_r = sum(t.realized_r for t in wins if t.realized_r > 0)
    gross_loss_r = abs(sum(t.realized_r for t in losses if t.realized_r < 0))

    return {
        "open_trades": open_count,
        "closed_trades": total,
        "win_rate": round(100.0 * len(wins) / total, 2),
        "average_r": round(total_r / total, 3),
        "total_r": round(total_r, 3),
        "best_trade_r": round(max(t.realized_r for t in closed), 3),
        "worst_trade_r": round(min(t.realized_r for t in closed), 3),
        "profit_factor": round(gross_win_r / gross_loss_r, 3) if gross_loss_r > 0 else None,
    }


# ---------------------------------------------------------------------------
# helpers internos
# ---------------------------------------------------------------------------

def _to_engine_direction(db_direction: DBDirection):
    from alphaquant_core.playbooks.base import Direction as EngineDirection
    return EngineDirection(db_direction.value)


def _targets_to_json(state: TradeState) -> list[dict]:
    return [
        {"price": t.price, "exit_pct": t.exit_pct, "rr": t.rr, "hit": t.hit,
         "hit_at": t.hit_at.isoformat() if t.hit_at else None, "hit_price": t.hit_price}
        for t in state.targets
    ]


def _rehydrate(trade: Trade) -> TradeState:
    """Reconstrói o TradeState puro a partir da linha `Trade` — inclusive
    após um restart do processo (seção 102: 'não perder operações')."""
    targets = [
        TargetLeg(
            price=float(t["price"]), exit_pct=float(t["exit_pct"]), rr=t.get("rr"),
            hit=bool(t.get("hit", False)),
            hit_at=datetime.fromisoformat(t["hit_at"]) if t.get("hit_at") else None,
            hit_price=t.get("hit_price"),
        )
        for t in trade.targets
    ]
    state = TradeState(
        asset=trade.asset,
        direction=_to_engine_direction(trade.direction),
        strategy_name=trade.strategy_name,
        entry=float(trade.entry),
        initial_stop=float(trade.initial_stop),
        targets=targets,
        opened_at=trade.opened_at,
        move_to_breakeven_after_tp1=trade.move_to_breakeven_after_tp1,
    )
    # __post_init__ reseta stop = initial_stop; restaura o stop já movido
    # (ex.: breakeven aplicado em um ciclo anterior) e o restante do estado.
    state.stop = float(trade.stop)
    state.status = EngineTradeStatus(trade.status.value)
    state.remaining_pct = trade.remaining_pct
    state.realized_pnl_pct = trade.realized_pnl_pct
    state.realized_r = trade.realized_r
    state.last_price = float(trade.last_price) if trade.last_price is not None else None
    state.closed_at = trade.closed_at
    # exit_reasons não é persistido diretamente — reconstruído a partir de
    # quais alvos já foram tocados (a ordem dos targets já reflete a
    # ordem de distância/TP, ver open_trade). Sem isso, o `result`
    # calculado após um restart classificaria incorretamente uma trade
    # com TP parcial + stop como WIN puro em vez de PARTIAL_WIN.
    state.exit_reasons = [
        _TP_REASON_BY_INDEX[i] for i, leg in enumerate(targets)
        if leg.hit and i < len(_TP_REASON_BY_INDEX)
    ]
    return state


def _writeback(db: Session, trade: Trade, state: TradeState, events: list) -> None:
    trade.stop = state.stop
    trade.targets = _targets_to_json(state)
    trade.status = DBTradeStatus(state.status.value)
    trade.remaining_pct = state.remaining_pct
    trade.realized_pnl_pct = state.realized_pnl_pct
    trade.realized_r = state.realized_r
    trade.last_price = state.last_price
    trade.last_price_at = events[-1].timestamp if events else trade.last_price_at
    if not state.is_open:
        trade.closed_at = state.closed_at
        if state.result is not None:
            trade.result = DBTradeResult(state.result.value)


def _persist_events(db: Session, trade: Trade, events: list) -> list[TradeEvent]:
    rows = [
        TradeEvent(
            trade_id=trade.id, event_type=e.event_type, price=e.price,
            timestamp=e.timestamp, event_metadata=e.metadata,
        )
        for e in events
    ]
    for row in rows:
        db.add(row)
    db.commit()
    db.refresh(trade)
    return rows
