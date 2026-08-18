"""
Backtest Engine (Fase 13 — seção 55 do master prompt).

Reavalia um Playbook candle a candle sobre o histórico já coletado pelo
Data Engine (tabela `candles`), usando em cada ponto **apenas** os dados
disponíveis até aquele momento (sem lookahead bias — a janela usada em
cada avaliação nunca inclui candles futuras em relação ao ponto
simulado). Quando um sinal aparece, simula o resultado forward: percorre
as candles seguintes até o preço bater o stop ou o primeiro alvo (TP1),
e classifica o trade como vitória/derrota/timeout.

Nenhuma estratégia deve ser considerada validada (`ACTIVE` na tabela
`playbooks`) sem passar por aqui — seção 55: "uma estratégia não deve ser
considerada validada apenas porque funcionou em poucas ocorrências."
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from alphaquant_core.engines.targets import compute_targets
from alphaquant_core.playbooks.base import Direction, Playbook
from alphaquant_core.playbooks.engine import build_context

MIN_LOOKBACK = 60  # candles mínimas para o contexto ter indicadores/estrutura utilizáveis
MAX_HOLD_BARS = 100  # após isso sem bater stop nem TP1, o trade conta como timeout (fora das estatísticas)


class TradeOutcome(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class SimulatedTrade:
    entry_index: int
    direction: Direction
    entry: float
    stop: float
    tp1: float
    outcome: TradeOutcome
    r_multiple: float  # positivo em vitória, negativo em derrota, 0 em timeout


@dataclass(frozen=True)
class BacktestStats:
    trades: int
    win_rate: float
    payoff: float          # média(ganho em R) / média(perda em R), sempre positivo
    profit_factor: float   # soma dos ganhos em R / soma das perdas em R
    expectancy: float      # expectativa em R por trade
    max_drawdown: float    # maior drawdown da curva de equity, em R


def _simulate_forward(df: pd.DataFrame, entry_index: int, direction: Direction, entry: float, stop: float, tp1: float) -> SimulatedTrade:
    risk = abs(entry - stop)
    horizon = df.iloc[entry_index + 1 : entry_index + 1 + MAX_HOLD_BARS]

    for _, candle in horizon.iterrows():
        if direction is Direction.LONG:
            hit_stop = candle["low"] <= stop
            hit_tp = candle["high"] >= tp1
        else:
            hit_stop = candle["high"] >= stop
            hit_tp = candle["low"] <= tp1

        # conservador: se a mesma candle tocar os dois, assume o pior caso (stop primeiro)
        if hit_stop:
            return SimulatedTrade(entry_index, direction, entry, stop, tp1, TradeOutcome.LOSS, -1.0)
        if hit_tp:
            r = abs(tp1 - entry) / risk if risk > 0 else 0.0
            return SimulatedTrade(entry_index, direction, entry, stop, tp1, TradeOutcome.WIN, r)

    return SimulatedTrade(entry_index, direction, entry, stop, tp1, TradeOutcome.TIMEOUT, 0.0)


def run_backtest(
    df: pd.DataFrame,
    playbook: Playbook,
    symbol: str,
    timeframe: str,
    lookback: int = 200,
) -> list[SimulatedTrade]:
    """
    Percorre `df` (candles ordenadas cronologicamente) avaliando
    `playbook` a cada ponto, usando só a janela `[i-lookback, i]` (nunca
    dados futuros). Devolve a lista de trades simulados — vazia se o
    playbook nunca bateu no período.
    """
    trades: list[SimulatedTrade] = []
    n = len(df)
    start = max(lookback, MIN_LOOKBACK)

    for i in range(start, n - 1):
        window = df.iloc[i - lookback : i + 1] if i - lookback >= 0 else df.iloc[: i + 1]
        if len(window) < MIN_LOOKBACK:
            continue

        ctx = build_context(symbol, timeframe, window)
        result = playbook.evaluate(ctx)
        if not result.matched or result.entry is None or result.stop is None:
            continue

        target_result = compute_targets(ctx.swings, result.direction, result.entry, result.stop)
        if target_result is None or target_result.tp1 is None:
            continue

        trade = _simulate_forward(df, i, result.direction, result.entry, result.stop, target_result.tp1)
        trades.append(trade)

    return trades


def compute_backtest_stats(trades: list[SimulatedTrade]) -> BacktestStats:
    """
    Calcula as estatísticas a partir de trades já decididos (WIN/LOSS) —
    TIMEOUT é excluído do cálculo (não sabemos o resultado real, não
    fabricamos um). Devolve tudo zerado se não houver trades decididos.
    """
    decided = [t for t in trades if t.outcome != TradeOutcome.TIMEOUT]
    if not decided:
        return BacktestStats(trades=0, win_rate=0.0, payoff=0.0, profit_factor=0.0, expectancy=0.0, max_drawdown=0.0)

    wins = [t.r_multiple for t in decided if t.outcome == TradeOutcome.WIN]
    losses = [abs(t.r_multiple) for t in decided if t.outcome == TradeOutcome.LOSS]

    win_rate = len(wins) / len(decided)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    payoff = avg_win / avg_loss if avg_loss > 0 else (avg_win if avg_win > 0 else 0.0)

    total_wins = sum(wins)
    total_losses = sum(losses)
    profit_factor = total_wins / total_losses if total_losses > 0 else (total_wins if total_wins > 0 else 0.0)

    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

    # equity curve em R, na ordem cronológica dos trades decididos
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in decided:
        equity += t.r_multiple
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    return BacktestStats(
        trades=len(decided), win_rate=win_rate, payoff=payoff,
        profit_factor=profit_factor, expectancy=expectancy, max_drawdown=max_dd,
    )
