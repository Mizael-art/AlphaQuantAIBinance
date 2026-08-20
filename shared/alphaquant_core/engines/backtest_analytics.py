"""
backtest_analytics — Fase 6 (seções 37-41): Monte Carlo, Walk Forward,
Sensitivity e Grid Test, construídos EM CIMA do Backtest Engine já
existente (`engines/backtest.py`) sem alterar sua lógica bar-a-bar
sem-lookahead — cada função aqui ou (a) reamostra estatisticamente
trades JÁ decididos por `run_backtest`, ou (b) chama `run_backtest`
várias vezes sobre janelas/parâmetros diferentes, nunca reimplementando
a simulação.

Nunca chamar nada disto de "previsão" (seção 37/72): Monte Carlo e
Walk Forward descrevem o que ACONTECEU sob reamostragem/período
diferente, não o que vai acontecer.
"""
from __future__ import annotations

import itertools
import random
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

import pandas as pd

from alphaquant_core.engines.backtest import BacktestStats, SimulatedTrade, compute_backtest_stats, run_backtest
from alphaquant_core.playbooks.base import Playbook
from alphaquant_core.strategies.strategy_parser import parse_prompt
from alphaquant_core.strategies.strategy_runner import PromptStrategy
from alphaquant_core.strategies.strategy_validator import validate_prompt


# ---------------------------------------------------------------------------
# Monte Carlo (seção 37)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MonteCarloResult:
    simulations: int
    trades_per_sim: int
    final_equity_r_p5: float
    final_equity_r_p50: float
    final_equity_r_p95: float
    max_drawdown_r_p50: float
    max_drawdown_r_p95: float
    probability_of_loss: float   # fração das simulações que terminam com equity < 0
    probability_of_ruin: float   # fração das simulações cujo drawdown atinge `ruin_drawdown_r`


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, round(p * (len(sorted_values) - 1))))
    return sorted_values[idx]


def run_monte_carlo(
    r_multiples: list[float],
    simulations: int = 1000,
    trades_per_sim: int | None = None,
    ruin_drawdown_r: float = 10.0,
    seed: int | None = None,
) -> MonteCarloResult:
    """
    Reamostra COM reposição os R-múltiplos de trades já decididos
    (WIN/LOSS reais do backtest) para simular sequências alternativas
    (seção 37: "usar trades históricos para simular equity/drawdown/
    sequências/probabilidade de perda/distribuição de resultados").

    Nunca usa dados futuros nem inventa trades — a reamostragem sai
    sempre do mesmo conjunto de resultados já observados.
    """
    if not r_multiples:
        raise ValueError("run_monte_carlo precisa de ao menos um R-múltiplo de trade decidido")
    if simulations <= 0:
        raise ValueError("simulations deve ser positivo")

    rng = random.Random(seed)
    n = trades_per_sim or len(r_multiples)

    finals: list[float] = []
    max_dds: list[float] = []
    losses = 0
    ruins = 0

    for _ in range(simulations):
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for _ in range(n):
            r = rng.choice(r_multiples)
            equity += r
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        finals.append(equity)
        max_dds.append(max_dd)
        if equity < 0:
            losses += 1
        if max_dd >= ruin_drawdown_r:
            ruins += 1

    finals.sort()
    max_dds.sort()

    return MonteCarloResult(
        simulations=simulations,
        trades_per_sim=n,
        final_equity_r_p5=_percentile(finals, 0.05),
        final_equity_r_p50=_percentile(finals, 0.50),
        final_equity_r_p95=_percentile(finals, 0.95),
        max_drawdown_r_p50=_percentile(max_dds, 0.50),
        max_drawdown_r_p95=_percentile(max_dds, 0.95),
        probability_of_loss=losses / simulations,
        probability_of_ruin=ruins / simulations,
    )


# ---------------------------------------------------------------------------
# Walk Forward (seção 38)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WalkForwardFold:
    fold_index: int
    dev_start: pd.Timestamp
    dev_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp
    dev_stats: BacktestStats
    oos_stats: BacktestStats


def run_walk_forward(
    df: pd.DataFrame,
    playbook: Playbook,
    symbol: str,
    timeframe: str,
    n_folds: int = 4,
    oos_fraction: float = 0.3,
    lookback: int = 60,
) -> list[WalkForwardFold]:
    """
    Divide `df` em `n_folds` blocos cronológicos sequenciais e NÃO
    sobrepostos; dentro de cada bloco, a fatia final (`oos_fraction`) é
    Out-of-Sample e a fatia inicial é Development (seção 38: "não
    otimizar parâmetros usando o mesmo período do teste final" — aqui
    isso significa que qualquer decisão sobre a estratégia deve olhar
    só para `dev_stats`; `oos_stats` é só para validar depois).

    Cada bloco é passado para `run_backtest` de forma independente e
    truncada no seu próprio fim — nenhum candle de um bloco posterior
    entra na simulação de um bloco anterior.
    """
    if n_folds <= 0:
        raise ValueError("n_folds deve ser positivo")
    if not (0.0 < oos_fraction < 1.0):
        raise ValueError("oos_fraction deve estar entre 0 e 1 (exclusive)")

    n = len(df)
    fold_size = n // n_folds
    if fold_size < lookback + 10:
        raise ValueError(
            f"dados insuficientes para {n_folds} folds com lookback={lookback} "
            f"(candles disponíveis: {n}, necessário >= {(lookback + 10) * n_folds})"
        )

    folds: list[WalkForwardFold] = []
    for f in range(n_folds):
        block_start = f * fold_size
        block_end = n if f == n_folds - 1 else (f + 1) * fold_size
        block = df.iloc[block_start:block_end]

        split = max(lookback + 1, int(len(block) * (1 - oos_fraction)))
        split = min(split, len(block) - 1)  # garante pelo menos 1 candle de OOS

        dev_block = block.iloc[:split]
        oos_block = block.iloc[split:]
        # o OOS reusa `lookback` candles do fim do dev como contexto (senão o
        # início do OOS não teria indicadores/estrutura utilizáveis), mas o
        # PONTO DE ENTRADA simulado só acontece dentro da janela OOS —
        # `run_backtest` já garante isso via `range(start, n-1)`.
        oos_block_with_context = block.iloc[max(0, split - lookback):]

        dev_trades = run_backtest(dev_block, playbook, symbol, timeframe, lookback=lookback)
        oos_trades = run_backtest(oos_block_with_context, playbook, symbol, timeframe, lookback=lookback)

        folds.append(WalkForwardFold(
            fold_index=f,
            dev_start=dev_block.index[0], dev_end=dev_block.index[-1],
            oos_start=oos_block.index[0], oos_end=oos_block.index[-1],
            dev_stats=compute_backtest_stats(dev_trades),
            oos_stats=compute_backtest_stats(oos_trades),
        ))

    return folds


# ---------------------------------------------------------------------------
# Sensitivity (seção 39) — específico a PromptStrategy, que expõe
# parâmetros numéricos explícitos no prompt (playbooks hardcoded não têm
# parâmetros endereçáveis de fora, então sensitivity não se aplica a eles).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SensitivityResult:
    param_overrides: dict[str, float]
    stats: BacktestStats


def run_sensitivity(
    base_prompt: str,
    param_grid: dict[str, Iterable[float]],
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    lookback: int = 60,
) -> list[SensitivityResult]:
    """
    `param_grid` mapeia um FIELD que aparece no prompt (ex.: "RSI14") a
    uma lista de valores para substituir no lugar do número original
    daquela condição (ex.: RSI14 < 40 -> RSI14 < 30, RSI14 < 50, ...).
    Roda o backtest para cada combinação da grade (produto cartesiano).

    Variantes que o parser/validator rejeitam (sintaxe quebrada pela
    substituição, ou campo que virou UNSUPPORTED) são simplesmente
    excluídas do resultado — nunca contam como "estratégia fraca", já
    que nem chegaram a ser uma estratégia executável (seção 15).
    """
    keys = list(param_grid.keys())
    value_lists = [list(param_grid[k]) for k in keys]

    results: list[SensitivityResult] = []
    for combo in itertools.product(*value_lists):
        overrides = dict(zip(keys, combo))
        prompt_text = base_prompt
        for field_name, value in overrides.items():
            pattern = rf"({re.escape(field_name)}(?:\([^)]*\))?\s*(?:==|!=|>=|<=|>|<)\s*)[\d.]+"
            prompt_text = re.sub(pattern, rf"\g<1>{value}", prompt_text)

        try:
            parsed = parse_prompt("sensitivity", prompt_text)
        except Exception:
            continue
        validation = validate_prompt(parsed)
        if not validation.valid:
            continue

        strategy = PromptStrategy(parsed)
        trades = run_backtest(df, strategy, symbol, timeframe, lookback=lookback)
        results.append(SensitivityResult(param_overrides=overrides, stats=compute_backtest_stats(trades)))

    return results


ROBUST = "ROBUST"
FRAGILE = "FRAGILE"
CONSISTENTLY_NEGATIVE = "CONSISTENTLY_NEGATIVE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


def assess_robustness(results: list[SensitivityResult], min_trades: int = 1) -> str:
    """
    ROBUST: expectancy positiva em toda variante testada (com trades
    suficientes) — a estratégia não depende de um valor mágico de
    parâmetro. FRAGILE: o sinal muda de lado dependendo do parâmetro.
    CONSISTENTLY_NEGATIVE: nenhuma variante é lucrativa (não é "robusta
    o suficiente para operar", só é estável em ser ruim).
    """
    usable = [r for r in results if r.stats.trades >= min_trades]
    if len(usable) < 2:
        return INSUFFICIENT_DATA

    positive = sum(1 for r in usable if r.stats.expectancy > 0)
    if positive == len(usable):
        return ROBUST
    if positive == 0:
        return CONSISTENTLY_NEGATIVE
    return FRAGILE


# ---------------------------------------------------------------------------
# Grid Test (seção 40)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GridCell:
    strategy_name: str
    playbook: Playbook
    symbol: str
    timeframe: str


@dataclass(frozen=True)
class GridResult:
    strategy_name: str
    symbol: str
    timeframe: str
    stats: BacktestStats
    skipped_reason: str | None = None


def run_grid_test(
    cells: list[GridCell],
    data_provider: Callable[[str, str], pd.DataFrame | None],
    lookback: int = 60,
    min_candles: int = 0,
) -> list[GridResult]:
    """
    Roda `run_backtest` para cada combinação (estratégia x ativo x
    timeframe) pedida (seção 40). `data_provider(symbol, timeframe)`
    devolve o DataFrame de candles já persistido (reaproveita o que o
    Data Engine já coletou — nunca busca dado novo aqui) ou `None`/vazio
    se não houver dado suficiente, caso em que a célula é reportada como
    pulada, nunca fabricada com zero silencioso.
    """
    results: list[GridResult] = []
    min_needed = max(min_candles, lookback + 10)

    for cell in cells:
        df = data_provider(cell.symbol, cell.timeframe)
        if df is None or len(df) < min_needed:
            results.append(GridResult(
                strategy_name=cell.strategy_name, symbol=cell.symbol, timeframe=cell.timeframe,
                stats=compute_backtest_stats([]),
                skipped_reason=f"dados insuficientes ({0 if df is None else len(df)} candles, mínimo {min_needed})",
            ))
            continue

        trades = run_backtest(df, cell.playbook, cell.symbol, cell.timeframe, lookback=lookback)
        results.append(GridResult(
            strategy_name=cell.strategy_name, symbol=cell.symbol, timeframe=cell.timeframe,
            stats=compute_backtest_stats(trades),
        ))

    return results


# ---------------------------------------------------------------------------
# Comparison (seção 41)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ComparisonRow:
    name: str
    stats: BacktestStats


def compare_strategies(results: dict[str, BacktestStats], sort_by: str = "expectancy") -> list[ComparisonRow]:
    valid_fields = {"trades", "win_rate", "payoff", "profit_factor", "expectancy", "max_drawdown"}
    if sort_by not in valid_fields:
        raise ValueError(f"sort_by deve ser um de {sorted(valid_fields)}")

    rows = [ComparisonRow(name=name, stats=stats) for name, stats in results.items()]
    reverse = sort_by != "max_drawdown"  # drawdown: menor é melhor, o resto: maior é melhor
    rows.sort(key=lambda r: getattr(r.stats, sort_by), reverse=reverse)
    return rows
