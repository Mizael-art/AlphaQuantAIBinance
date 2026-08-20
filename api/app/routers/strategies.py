"""
/strategies — Strategy Lab (seções 23-30). Toda a área é protegida
(seção 23-24): `require_admin` em cada rota.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from alphaquant_core.db.models import Strategy, StrategyStatus
from alphaquant_core.db.session import get_db
from alphaquant_core.engines.backtest import compute_backtest_stats, run_backtest
from alphaquant_core.engines.backtest_analytics import (
    assess_robustness,
    run_monte_carlo,
    run_sensitivity,
    run_walk_forward,
)
from alphaquant_core.engines.bybit_data_engine import BybitMarketDataClient
from alphaquant_core.engines.data_engine import MarketDataError
from alphaquant_core.engines.orchestrator import fetch_and_persist
from alphaquant_core.playbooks.backtest_runner import load_candles_df
from alphaquant_core.playbooks.engine import build_context
from alphaquant_core.services import strategy_service
from alphaquant_core.services.backtest_service import save_backtest_result
from alphaquant_core.strategies.strategy_parser import parse_prompt
from alphaquant_core.strategies.strategy_runner import PromptStrategy

from app.auth import require_admin

router = APIRouter(prefix="/strategies", tags=["strategies"], dependencies=[Depends(require_admin)])


class CreateStrategyRequest(BaseModel):
    name: str
    prompt: str
    mode: str = "SCANNER"
    active: bool = True


class UpdateStrategyRequest(BaseModel):
    prompt: str | None = None
    mode: str | None = None
    change_note: str | None = None


class TestStrategyRequest(BaseModel):
    asset: str
    timeframe: str = "1h"


class BacktestRequest(BaseModel):
    asset: str
    timeframe: str = "1h"
    lookback: int = 60


class MonteCarloRequest(BacktestRequest):
    simulations: int = 1000
    trades_per_sim: int | None = None
    ruin_drawdown_r: float = 10.0
    seed: int | None = None


class WalkForwardRequest(BacktestRequest):
    n_folds: int = 4
    oos_fraction: float = 0.3


class SensitivityRequest(BacktestRequest):
    param_grid: dict[str, list[float]]


def _get_or_404(db: Session, strategy_id: int) -> Strategy:
    strategy = strategy_service.get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="estratégia não encontrada")
    return strategy


def _require_runnable(strategy: Strategy) -> PromptStrategy:
    version = strategy.current_version
    if version.status != "VALID":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"estratégia não executável (status={version.status}): "
                   f"{version.errors + version.unsupported_conditions}",
        )
    parsed = parse_prompt(strategy.name, version.prompt_raw)
    return PromptStrategy(parsed, version=version.version_label)


def _load_candles_or_422(db: Session, asset: str, timeframe: str, min_candles: int):
    df = load_candles_df(db, asset, timeframe)
    if len(df) < min_candles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"apenas {len(df)} candles persistidas para {asset.upper()} {timeframe} "
                   f"(mínimo {min_candles}) — deixe o scanner rodar mais tempo ou reduza lookback/ajuste o período",
        )
    return df


def _stats_dict(stats) -> dict:
    return {
        "trades": stats.trades, "win_rate": stats.win_rate, "payoff": stats.payoff,
        "profit_factor": stats.profit_factor, "expectancy": stats.expectancy, "max_drawdown": stats.max_drawdown,
    }


@router.get("")
def list_strategies(db: Session = Depends(get_db)) -> dict:
    return {"strategies": [strategy_service.to_dict(s) for s in strategy_service.list_strategies(db)]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_strategy(
    payload: CreateStrategyRequest, db: Session = Depends(get_db), user: str = Depends(require_admin),
) -> dict:
    strategy = strategy_service.create_strategy(
        db, name=payload.name, prompt_raw=payload.prompt, mode=payload.mode,
        active=payload.active, author=user,
    )
    return strategy_service.to_dict(strategy)


@router.get("/{strategy_id}")
def get_strategy(strategy_id: int, db: Session = Depends(get_db)) -> dict:
    strategy = _get_or_404(db, strategy_id)
    return strategy_service.to_dict(strategy)


@router.get("/{strategy_id}/versions")
def list_versions(strategy_id: int, db: Session = Depends(get_db)) -> dict:
    strategy = _get_or_404(db, strategy_id)
    return {
        "versions": [
            {
                "id": v.id, "version_label": v.version_label, "prompt_raw": v.prompt_raw,
                "status": v.status, "errors": v.errors, "unsupported_conditions": v.unsupported_conditions,
                "author": v.author, "change_note": v.change_note, "created_at": v.created_at.isoformat(),
                "is_current": v.id == strategy.current_version_id,
            }
            for v in strategy.versions
        ]
    }


@router.patch("/{strategy_id}")
def update_strategy(
    strategy_id: int, payload: UpdateStrategyRequest,
    db: Session = Depends(get_db), user: str = Depends(require_admin),
) -> dict:
    strategy = _get_or_404(db, strategy_id)
    strategy = strategy_service.update_strategy(
        db, strategy, prompt_raw=payload.prompt, mode=payload.mode,
        author=user, change_note=payload.change_note,
    )
    return strategy_service.to_dict(strategy)


@router.post("/{strategy_id}/activate")
def activate_strategy(strategy_id: int, db: Session = Depends(get_db)) -> dict:
    strategy = _get_or_404(db, strategy_id)
    return strategy_service.to_dict(strategy_service.set_status(db, strategy, StrategyStatus.ACTIVE))


@router.post("/{strategy_id}/deactivate")
def deactivate_strategy(strategy_id: int, db: Session = Depends(get_db)) -> dict:
    strategy = _get_or_404(db, strategy_id)
    return strategy_service.to_dict(strategy_service.set_status(db, strategy, StrategyStatus.INACTIVE))


@router.delete("/{strategy_id}")
def archive_strategy(strategy_id: int, db: Session = Depends(get_db)) -> dict:
    """DELETAR == ARCHIVE (seção 29) — nunca remove histórico."""
    strategy = _get_or_404(db, strategy_id)
    return strategy_service.to_dict(strategy_service.archive_strategy(db, strategy))


@router.post("/{strategy_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_strategy(strategy_id: int, db: Session = Depends(get_db)) -> dict:
    strategy = _get_or_404(db, strategy_id)
    return strategy_service.to_dict(strategy_service.duplicate_strategy(db, strategy))


@router.post("/{strategy_id}/test")
def test_strategy(strategy_id: int, payload: TestStrategyRequest, db: Session = Depends(get_db)) -> dict:
    """
    Seção 30 (versão "rápida" — histórico longo/Monte Carlo/walk-forward
    ficam na Fase 6 de Backtest): roda a estratégia contra o
    MarketContext ATUAL de um ativo/timeframe, sem enviar Telegram nem
    criar Trade — só devolve se bateria ou não agora, e por quê.
    """
    strategy = _get_or_404(db, strategy_id)
    version = strategy.current_version
    if version.status != "VALID":
        return {
            "runnable": False,
            "status": version.status,
            "errors": version.errors,
            "unsupported_conditions": version.unsupported_conditions,
        }

    try:
        client = BybitMarketDataClient()
        df, candles, _ = fetch_and_persist(db, payload.asset, payload.timeframe, client=client)
    except MarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    ctx = build_context(payload.asset.upper(), payload.timeframe, df)
    parsed = parse_prompt(strategy.name, version.prompt_raw)
    runner = PromptStrategy(parsed, version=version.version_label)
    result = runner.evaluate(ctx)

    return {
        "runnable": True,
        "asset": payload.asset.upper(),
        "timeframe": payload.timeframe,
        "matched": result.matched,
        "direction": result.direction.value if result.direction else None,
        "progress": result.progress,
        "conditions_met": result.conditions_met,
        "conditions_missing": result.conditions_missing,
        "entry": result.entry,
        "stop": result.stop,
        "notes": result.notes,
        "last_close": candles[-1].close if candles else None,
    }


@router.post("/{strategy_id}/backtest")
def backtest_strategy(strategy_id: int, payload: BacktestRequest, db: Session = Depends(get_db)) -> dict:
    """
    Seções 30-36 — histórico longo (limitado só pelo que o Data Engine já
    persistiu para esse ativo/timeframe; seção 31 pede pelo menos 1 ano
    quando disponível). Persiste o resultado em `backtests` como os
    playbooks hardcoded já fazem (mesma tabela, seção 55).
    """
    strategy = _get_or_404(db, strategy_id)
    runner = _require_runnable(strategy)
    df = _load_candles_or_422(db, payload.asset, payload.timeframe, payload.lookback + 50)

    trades = run_backtest(df, runner, payload.asset.upper(), payload.timeframe, lookback=payload.lookback)
    stats = compute_backtest_stats(trades)
    save_backtest_result(db, strategy.name, payload.asset.upper(), payload.timeframe, stats)

    return {
        "asset": payload.asset.upper(), "timeframe": payload.timeframe,
        "period": {"start": df.index[0].isoformat(), "end": df.index[-1].isoformat(), "candles": len(df)},
        "stats": _stats_dict(stats),
    }


@router.post("/{strategy_id}/backtest/monte-carlo")
def monte_carlo_strategy(strategy_id: int, payload: MonteCarloRequest, db: Session = Depends(get_db)) -> dict:
    """Seção 37 — reamostra os trades decididos do backtest. Nunca chamado
    de previsão: só descreve variação possível sobre o que já aconteceu."""
    strategy = _get_or_404(db, strategy_id)
    runner = _require_runnable(strategy)
    df = _load_candles_or_422(db, payload.asset, payload.timeframe, payload.lookback + 50)

    trades = run_backtest(df, runner, payload.asset.upper(), payload.timeframe, lookback=payload.lookback)
    r_multiples = [t.r_multiple for t in trades if t.outcome.value != "TIMEOUT"]
    if not r_multiples:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="nenhum trade decidido (WIN/LOSS) nesse período — sem base para Monte Carlo",
        )

    result = run_monte_carlo(
        r_multiples, simulations=payload.simulations, trades_per_sim=payload.trades_per_sim,
        ruin_drawdown_r=payload.ruin_drawdown_r, seed=payload.seed,
    )
    return {
        "based_on_trades": len(r_multiples),
        "simulations": result.simulations, "trades_per_sim": result.trades_per_sim,
        "final_equity_r": {"p5": result.final_equity_r_p5, "p50": result.final_equity_r_p50, "p95": result.final_equity_r_p95},
        "max_drawdown_r": {"p50": result.max_drawdown_r_p50, "p95": result.max_drawdown_r_p95},
        "probability_of_loss": result.probability_of_loss,
        "probability_of_ruin": result.probability_of_ruin,
    }


@router.post("/{strategy_id}/backtest/walk-forward")
def walk_forward_strategy(strategy_id: int, payload: WalkForwardRequest, db: Session = Depends(get_db)) -> dict:
    """Seção 38 — Development vs Out-of-Sample por fold, nunca otimizado
    no mesmo período do teste final (isso fica a cargo de quem lê os
    resultados: só `dev_stats` deve informar qualquer ajuste de prompt)."""
    strategy = _get_or_404(db, strategy_id)
    runner = _require_runnable(strategy)
    min_needed = (payload.lookback + 10) * payload.n_folds
    df = _load_candles_or_422(db, payload.asset, payload.timeframe, min_needed)

    try:
        folds = run_walk_forward(
            df, runner, payload.asset.upper(), payload.timeframe,
            n_folds=payload.n_folds, oos_fraction=payload.oos_fraction, lookback=payload.lookback,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return {
        "folds": [
            {
                "fold_index": f.fold_index,
                "dev_period": {"start": f.dev_start.isoformat(), "end": f.dev_end.isoformat()},
                "oos_period": {"start": f.oos_start.isoformat(), "end": f.oos_end.isoformat()},
                "dev_stats": _stats_dict(f.dev_stats),
                "oos_stats": _stats_dict(f.oos_stats),
            }
            for f in folds
        ]
    }


@router.post("/{strategy_id}/backtest/sensitivity")
def sensitivity_strategy(strategy_id: int, payload: SensitivityRequest, db: Session = Depends(get_db)) -> dict:
    """Seção 39 — varia parâmetros numéricos do próprio prompt (ex.:
    {"RSI14": [30, 40, 50]}) e classifica ROBUST/FRAGILE/CONSISTENTLY_NEGATIVE."""
    strategy = _get_or_404(db, strategy_id)
    version = strategy.current_version
    if version.status != "VALID":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"estratégia não executável (status={version.status})")
    if not payload.param_grid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="param_grid vazio")

    df = _load_candles_or_422(db, payload.asset, payload.timeframe, payload.lookback + 50)

    results = run_sensitivity(
        version.prompt_raw, payload.param_grid, df, payload.asset.upper(), payload.timeframe,
        lookback=payload.lookback,
    )
    if not results:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="nenhuma variante do param_grid produziu uma estratégia válida",
        )

    return {
        "robustness": assess_robustness(results),
        "variants": [
            {"param_overrides": r.param_overrides, "stats": _stats_dict(r.stats)}
            for r in results
        ],
    }
