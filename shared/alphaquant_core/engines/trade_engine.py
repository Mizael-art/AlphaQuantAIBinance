"""
trade_engine — Fase 2 (doc "OPERAÇÕES E HISTÓRICO DE SINAIS", seções
77-106): motor PURO (sem I/O, sem banco) que acompanha uma operação
hipotética nascida de um sinal CONFIRMED do AlphaQuant X.

Importante (secao 79/97): isto NUNCA executa ordem nem representa PnL de
conta real — e' o acompanhamento matematico do que teria acontecido se o
sinal fosse seguido, exatamente como o proprio sinal foi calculado (sem
lookahead: cada chamada a `update_price` so' enxerga o preco daquele
instante, nunca um preco futuro).

separacao SIGNAL vs TRADE (secao 96): este modulo so' conhece o TRADE.
Quem cria um TradeState a partir de uma Opportunity/PlaybookResult
confirmados e' a camada de persistencia (services/trade_service.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from alphaquant_core.playbooks.base import Direction

# Tolerancia para classificar um fechamento como BREAKEVEN em vez de
# WIN/LOSS marginal (ruido de ponto flutuante / R muito perto de 0).
BREAKEVEN_R_TOLERANCE = 0.05


class TradeStatus(str, Enum):
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


class TradeResult(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    PARTIAL_WIN = "PARTIAL_WIN"
    PARTIAL_LOSS = "PARTIAL_LOSS"


class ExitReason(str, Enum):
    TP1 = "TP1"
    TP2 = "TP2"
    TP3 = "TP3"
    TP4 = "TP4"
    TP5 = "TP5"
    STOP = "STOP"
    INVALIDATED = "INVALIDATED"
    MANUAL = "MANUAL"
    EXPIRED = "EXPIRED"


_TP_STATUS_BY_INDEX = [
    TradeStatus.TP1_HIT, TradeStatus.TP2_HIT, TradeStatus.TP3_HIT,
    TradeStatus.TP4_HIT, TradeStatus.TP5_HIT,
]
_TP_REASON_BY_INDEX = [
    ExitReason.TP1, ExitReason.TP2, ExitReason.TP3, ExitReason.TP4, ExitReason.TP5,
]


@dataclass
class TargetLeg:
    price: float
    exit_pct: float          # % da posicao encerrada quando este alvo e' tocado (secao 89)
    rr: float | None = None  # multiplo de R declarado pela estrategia (informativo)
    hit: bool = False
    hit_at: datetime | None = None
    hit_price: float | None = None


@dataclass
class TradeEvent:
    event_type: str          # TRADE_CREATED | PRICE_UPDATE | TP1_HIT | STOP_HIT | INVALIDATED | CLOSED | STOP_MOVED_TO_BREAKEVEN
    timestamp: datetime
    price: float
    metadata: dict = field(default_factory=dict)


@dataclass
class TradeState:
    """Estado mutavel de UMA operacao hipotetica (secao 96: TRADE, nao SIGNAL)."""
    asset: str
    direction: Direction
    strategy_name: str
    entry: float
    initial_stop: float
    targets: list[TargetLeg]
    opened_at: datetime
    move_to_breakeven_after_tp1: bool = False

    stop: float = field(init=False)
    remaining_pct: float = field(default=100.0, init=False)
    status: TradeStatus = field(default=TradeStatus.OPEN, init=False)
    realized_pnl_pct: float = field(default=0.0, init=False)  # ponderado pelas parcelas ja encerradas
    realized_r: float = field(default=0.0, init=False)
    exit_reasons: list[ExitReason] = field(default_factory=list, init=False)
    last_price: float | None = field(default=None, init=False)
    closed_at: datetime | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.stop = self.initial_stop

    # ------------------------------------------------------------------
    @property
    def risk(self) -> float:
        return abs(self.entry - self.initial_stop)

    @property
    def is_open(self) -> bool:
        return self.status not in (
            TradeStatus.CLOSED, TradeStatus.EXPIRED, TradeStatus.INVALIDATED, TradeStatus.STOP_HIT,
        )

    def unrealized_pnl_pct(self, current_price: float) -> float:
        if self.direction is Direction.LONG:
            return (current_price - self.entry) / self.entry * 100.0
        return (self.entry - current_price) / self.entry * 100.0

    def unrealized_r(self, current_price: float) -> float | None:
        if self.risk == 0:
            return None
        if self.direction is Direction.LONG:
            return (current_price - self.entry) / self.risk
        return (self.entry - current_price) / self.risk

    def distance_to_stop_pct(self, current_price: float) -> float:
        return abs(current_price - self.stop) / current_price * 100.0

    def distance_to_next_target_pct(self, current_price: float) -> float | None:
        nxt = next((t for t in self.targets if not t.hit), None)
        if nxt is None:
            return None
        return abs(nxt.price - current_price) / current_price * 100.0

    # ------------------------------------------------------------------
    def _pnl_pct_at(self, price: float) -> float:
        if self.direction is Direction.LONG:
            return (price - self.entry) / self.entry * 100.0
        return (self.entry - price) / self.entry * 100.0

    def _r_at(self, price: float) -> float:
        if self.risk == 0:
            return 0.0
        if self.direction is Direction.LONG:
            return (price - self.entry) / self.risk
        return (self.entry - price) / self.risk

    def _touched(self, price: float, level: float, *, is_stop: bool) -> bool:
        """Sem lookahead: so' compara o preco JA' recebido nesta chamada
        contra o nivel. Nao olha high/low futuro nem candles adiante."""
        long_ = self.direction is Direction.LONG
        if is_stop:
            return price <= level if long_ else price >= level
        return price >= level if long_ else price <= level

    def _close_remaining(self, price: float, timestamp: datetime, reason: ExitReason) -> TradeEvent:
        closing_pct = self.remaining_pct
        leg_r = self._r_at(price) * (closing_pct / 100.0)
        leg_pnl = self._pnl_pct_at(price) * (closing_pct / 100.0)
        self.realized_r += leg_r
        self.realized_pnl_pct += leg_pnl
        self.exit_reasons.append(reason)
        self.remaining_pct = 0.0
        self.status = TradeStatus.STOP_HIT if reason == ExitReason.STOP else TradeStatus.CLOSED
        self.closed_at = timestamp
        return TradeEvent(
            event_type=reason.value if reason == ExitReason.STOP else "CLOSED",
            timestamp=timestamp, price=price,
            metadata={"exit_pct": closing_pct, "leg_r": leg_r, "leg_pnl_pct": leg_pnl},
        )

    def update_price(self, price: float, timestamp: datetime | None = None) -> list[TradeEvent]:
        """
        Avaliada uma vez por ciclo (secao 86: a cada 15 minutos) com o
        preco mais recente. Nunca reordena nem olha eventos futuros —
        cada chamada e' independente e usa somente `price` recebido
        agora. Devolve a lista de eventos gerados nesta chamada (pode
        ser vazia).
        """
        timestamp = timestamp or datetime.now(timezone.utc)
        self.last_price = price
        events: list[TradeEvent] = []

        if not self.is_open:
            return events

        # 1) stop tem prioridade sobre TP no mesmo tick — nunca inventamos
        #    qual "aconteceu primeiro" dentro da mesma candle (secao 32:
        #    sem lookahead intrabar); tratar stop primeiro e' a leitura
        #    mais conservadora (nunca superestima o resultado).
        if self._touched(price, self.stop, is_stop=True):
            events.append(self._close_remaining(price, timestamp, ExitReason.STOP))
            events.append(self._finalize_result_event(timestamp))
            return events

        for i, leg in enumerate(self.targets):
            if leg.hit:
                continue
            if not self._touched(price, leg.price, is_stop=False):
                break  # alvos sao ordenados por distancia; se este nao bateu, os seguintes tambem nao
            leg.hit = True
            leg.hit_at = timestamp
            leg.hit_price = price

            leg_r = self._r_at(price) * (leg.exit_pct / 100.0)
            leg_pnl = self._pnl_pct_at(price) * (leg.exit_pct / 100.0)
            self.realized_r += leg_r
            self.realized_pnl_pct += leg_pnl
            self.remaining_pct = max(0.0, self.remaining_pct - leg.exit_pct)

            reason = _TP_REASON_BY_INDEX[i] if i < len(_TP_REASON_BY_INDEX) else ExitReason.MANUAL
            self.exit_reasons.append(reason)
            self.status = _TP_STATUS_BY_INDEX[i] if i < len(_TP_STATUS_BY_INDEX) else TradeStatus.TP5_HIT
            events.append(TradeEvent(
                event_type=f"{reason.value}_HIT", timestamp=timestamp, price=price,
                metadata={"exit_pct": leg.exit_pct, "leg_r": leg_r, "leg_pnl_pct": leg_pnl,
                          "remaining_pct": self.remaining_pct},
            ))

            if i == 0 and self.move_to_breakeven_after_tp1 and self.stop != self.entry:
                self.stop = self.entry
                events.append(TradeEvent(
                    event_type="STOP_MOVED_TO_BREAKEVEN", timestamp=timestamp, price=price,
                    metadata={"new_stop": self.entry},
                ))

            if self.remaining_pct <= 1e-9:
                self.status = TradeStatus.CLOSED
                self.closed_at = timestamp
                events.append(TradeEvent(event_type="CLOSED", timestamp=timestamp, price=price, metadata={}))
                break

        return events

    def invalidate(self, price: float, reason: str, timestamp: datetime | None = None) -> list[TradeEvent]:
        """Estrutura invalidou o setup antes do stop ou de todos os TPs
        serem tocados (secao 44/87) — fecha a parcela restante ao preco
        atual, nunca ao stop teorico (isso inflaria/deflacionaria o
        resultado de forma artificial)."""
        timestamp = timestamp or datetime.now(timezone.utc)
        if not self.is_open:
            return []
        close_event = self._close_remaining(price, timestamp, ExitReason.INVALIDATED)
        self.status = TradeStatus.INVALIDATED
        close_event.metadata["reason"] = reason
        return [close_event, self._finalize_result_event(timestamp)]

    def expire(self, price: float, timestamp: datetime | None = None) -> list[TradeEvent]:
        timestamp = timestamp or datetime.now(timezone.utc)
        if not self.is_open:
            return []
        self.status = TradeStatus.EXPIRED
        self.closed_at = timestamp
        return [TradeEvent(event_type="EXPIRED", timestamp=timestamp, price=price, metadata={})]

    def _finalize_result_event(self, timestamp: datetime) -> TradeEvent:
        return TradeEvent(
            event_type="RESULT", timestamp=timestamp, price=self.last_price or self.entry,
            metadata={"result": self.result.value, "realized_r": self.realized_r,
                      "realized_pnl_pct": self.realized_pnl_pct},
        )

    @property
    def result(self) -> TradeResult | None:
        """secao 88: WIN | LOSS | BREAKEVEN | PARTIAL_WIN | PARTIAL_LOSS.
        None enquanto a operacao ainda estiver aberta."""
        if self.is_open:
            return None
        partial = len(self.exit_reasons) > 1
        if abs(self.realized_r) <= BREAKEVEN_R_TOLERANCE:
            return TradeResult.BREAKEVEN
        if self.realized_r > 0:
            return TradeResult.PARTIAL_WIN if partial else TradeResult.WIN
        return TradeResult.PARTIAL_LOSS if partial else TradeResult.LOSS


def open_trade(
    asset: str, direction: Direction, strategy_name: str,
    entry: float, stop: float, targets: list[TargetLeg],
    opened_at: datetime | None = None, move_to_breakeven_after_tp1: bool = False,
) -> TradeState:
    if not targets:
        raise ValueError("uma operacao precisa de ao menos um alvo (TP)")
    total_pct = sum(t.exit_pct for t in targets)
    if total_pct <= 0 or total_pct > 100.0 + 1e-6:
        raise ValueError(f"soma dos exit_pct dos alvos deve ficar em (0, 100]: recebido {total_pct}")

    ordered = sorted(
        targets,
        key=lambda t: (t.price - entry) if direction is Direction.LONG else (entry - t.price),
    )
    return TradeState(
        asset=asset, direction=direction, strategy_name=strategy_name,
        entry=entry, initial_stop=stop, targets=ordered,
        opened_at=opened_at or datetime.now(timezone.utc),
        move_to_breakeven_after_tp1=move_to_breakeven_after_tp1,
    )
