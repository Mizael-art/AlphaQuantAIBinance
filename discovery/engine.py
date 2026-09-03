"""
discovery/engine.py
======================

Orquestração do Discovery/Ranking Engine (Documento 2, seções 4-12, 20;
Documento Master, seções 4-14). Reaproveita `app.run_analysis` (mesmo
pipeline usado por `/snapshot` e `/scan`) para trend/estrutura/score, e
busca candles brutos uma vez a mais por símbolo (via `MarketData`) só
para as métricas que `run_analysis` não expõe (percentil de
volatilidade, largura de Bollinger, retorno para força relativa).

Fluxo por símbolo: regime -> força relativa vs. BTC -> contexto BTC ->
filtro regime-first do Playbook (pula o símbolo se nada for
compatível -- nunca força um match) -> estimativa de entrada/stop/TP a
partir das zonas já calculadas -> Multi-Score. Depois de processar
todos os símbolos: Correlated Exposure Engine sobre os candidatos
rankeados, re-score dos penalizados, corte no `top_n`.

Nota (mesma convenção do `scanner/screener.py` já existente no repo):
esta função de orquestração faz chamadas de rede reais (via
`MarketData`/`run_analysis`) e não é coberta por teste de unidade --
os testes cobrem as peças puras (`regime/`, `scoring/`, `playbook/`,
`discovery/correlation.py`).

LIMITAÇÃO declarada: a estimativa de entrada/stop/TP aqui é um
primeiro corte a partir das zonas de suporte/resistência já calculadas
-- não é o "Trade Plan Generator" completo do Documento Master (seção
17), que fica para uma fase futura. Suficiente para RANQUEAR
oportunidades, não para ser tomado como plano de execução definitivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from api.market_data import MarketData
from app import InsufficientDataError, run_analysis
from indicators.atr import calculate_atr
from indicators.bands_channels import calculate_bollinger_bands
from statistics_.volatility import calculate_percentile_rank
from regime.btc_filter import classify_btc_context
from regime.detector import RegimeResult, detect_regime
from regime.relative_strength import classify_relative_strength
from playbook.library import PlaybookEntry, compatible_playbooks
from scanner.screener import _nearest_zone
from scoring.engine import OpportunityScore, compute_opportunity_score
from discovery.correlation import compute_return_correlation, flag_correlated_duplicates

_RETURN_LOOKBACK_CANDLES = 20
_REGIME_LOOKBACK_PERIOD = 100


@dataclass(frozen=True, slots=True)
class OpportunityResult:
    symbol: str
    direction: str
    playbook: str
    style: str
    regime: str
    btc_context: str | None
    price: float
    entry_zone: tuple[float, float] | None
    stop: float | None
    target: float | None
    rr: float | None
    distance_to_zone_pct: float | None
    score: OpportunityScore
    correlated_with: str | None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "playbook": self.playbook,
            "style": self.style,
            "regime": self.regime,
            "btc_context": self.btc_context,
            "price": self.price,
            "entry_zone": {"low": self.entry_zone[0], "high": self.entry_zone[1]} if self.entry_zone else None,
            "stop": self.stop,
            "target": self.target,
            "rr": self.rr,
            "distance_to_zone_pct": self.distance_to_zone_pct,
            "correlated_with": self.correlated_with,
            **self.score.to_dict(),
            "notes": self.notes,
        }


def _asset_regime_and_context(symbol: str, timeframe: str, market_data: MarketData) -> tuple[Any, RegimeResult, float, Any]:
    """Retorna (run_analysis result, RegimeResult, retorno % no lookback, DataFrame OHLCV) para um símbolo/timeframe."""
    result = run_analysis(symbol=symbol, timeframe=timeframe, market_data=market_data)
    df = market_data.get_ohlcv_dataframe(symbol=symbol, timeframe=timeframe)

    lookback = min(_REGIME_LOOKBACK_PERIOD, len(df))
    atr_series = calculate_atr(df, 14)
    vol_percentile = calculate_percentile_rank(atr_series, period=lookback).iloc[-1]

    bb = calculate_bollinger_bands(df, period=20, std_dev=2.0)
    bb_width = (bb.upper - bb.lower) / bb.middle
    bb_width_percentile = calculate_percentile_rank(bb_width, period=lookback).iloc[-1]

    price_percentile = calculate_percentile_rank(df["close"], period=lookback).iloc[-1]

    regime_result = detect_regime(
        trend=result.trend,
        bos=result.structure.bos,
        choch=result.structure.choch,
        volatility_percentile=float(vol_percentile) if vol_percentile == vol_percentile else 50.0,  # NaN-safe
        bb_width_percentile=float(bb_width_percentile) if bb_width_percentile == bb_width_percentile else 50.0,
        price_percentile_in_range=float(price_percentile) if price_percentile == price_percentile else 50.0,
    )

    n = min(_RETURN_LOOKBACK_CANDLES, len(df) - 1)
    return_pct = float((df["close"].iloc[-1] / df["close"].iloc[-1 - n] - 1) * 100) if n > 0 else 0.0

    return result, regime_result, return_pct, df


def _estimate_trade_levels(
    direction: str, price: float, support: list[float], resistance: list[float]
) -> tuple[tuple[float, float] | None, float | None, float | None, float | None]:
    """Estimativa de primeiro corte (ver limitação no docstring do módulo). Retorna (entry_zone, stop, target, distance_to_zone_pct)."""
    nearest_price, nearest_type, distance_pct = _nearest_zone(price, support, resistance)
    if nearest_price is None:
        return None, None, None, None

    zone_width = abs(price * 0.002)  # zona estreita em torno do nível -- estimativa conservadora, não uma otimização.
    entry_zone = (round(nearest_price - zone_width, 6), round(nearest_price + zone_width, 6))

    if direction == "long":
        stop_candidates = [s for s in support if s < nearest_price]
        target_candidates = sorted([r for r in resistance if r > nearest_price])
    else:
        stop_candidates = [s for s in resistance if s > nearest_price]
        target_candidates = sorted([r for r in support if r < nearest_price], reverse=True)

    stop = (min(stop_candidates) if direction == "long" else max(stop_candidates)) if stop_candidates else None
    target = target_candidates[0] if target_candidates else None

    return entry_zone, stop, target, distance_pct


GLOBAL_MIN_RR: float = 2.0



def _build_indicator_context(result: Any, df: Any, timeframe: str) -> dict[str, Any]:
    """Extrai indicadores técnicos e níveis estruturais do DataFrame e do resultado de análise."""
    price = float(df["close"].iloc[-1])
    atr_series = calculate_atr(df, 14)
    atr = float(atr_series.iloc[-1]) if len(atr_series) > 0 and atr_series.iloc[-1] == atr_series.iloc[-1] else price * 0.02

    ema20 = float(df["close"].ewm(span=20).mean().iloc[-1])
    ema50 = float(df["close"].ewm(span=50).mean().iloc[-1])
    ema100 = float(df["close"].ewm(span=100).mean().iloc[-1])
    ema200 = float(df["close"].ewm(span=200).mean().iloc[-1])

    vol_avg = float(df["volume"].rolling(20).mean().iloc[-1]) if "volume" in df else 1.0
    vol_current = float(df["volume"].iloc[-1]) if "volume" in df else 1.0
    vol_expansion = vol_current > (vol_avg * 1.25)

    swing_low = float(df["low"].tail(30).min())
    swing_high = float(df["high"].tail(30).max())

    return {
        "price": price,
        "atr": atr,
        "ema20": ema20,
        "ema50": ema50,
        "ema100": ema100,
        "ema200": ema200,
        "rsi": result.rsi if hasattr(result, "rsi") else 50.0,
        "macd": result.macd if hasattr(result, "macd") else 0.0,
        "macd_signal": result.macd_signal if hasattr(result, "macd_signal") else 0.0,
        "trend": result.trend,
        "bos": result.structure.bos,
        "choch": result.structure.choch,
        "support": result.support,
        "resistance": result.resistance,
        "swing_low": swing_low,
        "swing_high": swing_high,
        "volume_avg": vol_avg,
        "volume_current": vol_current,
        "vol_expansion": vol_expansion,
        "timeframe": timeframe,
    }


def scan_opportunities(
    symbols: list[str],
    btc_symbol: str = "BTCUSDT",
    direction: str | None = None,
    style: str | None = None,
    timeframe: str = "1H",
    top_n: int = 5,
    min_rr_filter: float | None = None,
    market_data: MarketData | None = None,
) -> dict[str, Any]:
    """
    Descoberta e rankeamento determinístico de oportunidades com:
    - Execução real dos Playbooks determinísticos
    - Hard Gate de RR Mínimo (max(GLOBAL_MIN_RR, playbook.min_rr))
    - Target Engine estrutural (sem fabricação de alvos ou stops)
    - Directional Conflict Resolution (LONG vs SHORT para o mesmo ativo)
    - 3-Score Engine (Setup 60%, Entry 40%, Trade Score)
    """
    md = market_data or MarketData()
    directions_to_try = [direction] if direction else ["long", "short"]
    effective_global_min_rr = min_rr_filter if min_rr_filter is not None else GLOBAL_MIN_RR

    btc_result, btc_regime, btc_return_pct, _btc_df = _asset_regime_and_context(btc_symbol, timeframe, md)

    raw_candidates_by_symbol: dict[str, list[OpportunityResult]] = {}
    no_edge: list[dict] = []
    returns_by_symbol: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for symbol in symbols:
        symbol = symbol.strip().upper()
        try:
            result, regime_result, return_pct, df = _asset_regime_and_context(symbol, timeframe, md)
        except InsufficientDataError as exc:
            errors[symbol] = str(exc)
            continue
        except Exception as exc:
            errors[symbol] = f"Erro na análise de {symbol}: {exc}"
            continue

        returns_by_symbol[symbol] = df["close"].pct_change().dropna().reset_index(drop=True)
        rel_strength = classify_relative_strength(return_pct, btc_return_pct)
        ctx = _build_indicator_context(result, df, timeframe)
        ctx["regime"] = regime_result.regime

        found_for_symbol = False
        symbol_candidates: list[OpportunityResult] = []

        for candidate_direction in directions_to_try:
            btc_context = (
                None
                if symbol == btc_symbol
                else classify_btc_context(btc_regime.regime, rel_strength.label, candidate_direction)
            )

            playbooks = compatible_playbooks(regime_result.regime, candidate_direction, style)
            if not playbooks:
                continue

            for playbook in playbooks:
                eval_res = playbook.evaluator(ctx)
                if not eval_res.matched:
                    continue

                # 1. Definir Níveis Técnicos Estruturais
                price = result.price
                atr = ctx["atr"]
                entry_zone = eval_res.entry_zone
                stop = eval_res.stop
                target = eval_res.tp1

                # Se o evaluator não forneceu níveis estruturais completos, derivar do suporte/resistência real
                if entry_zone is None or stop is None or target is None:
                    est_entry, est_stop, est_target, _ = _estimate_trade_levels(
                        candidate_direction, price, result.support, result.resistance
                    )
                    entry_zone = entry_zone or est_entry
                    stop = stop or est_stop
                    target = target or est_target

                if entry_zone is None or stop is None or target is None:
                    continue

                entry_price = (entry_zone[0] + entry_zone[1]) / 2.0 if entry_zone else price
                distance_pct = abs(price - entry_price) / price * 100 if price > 0 else 0.0

                # 2. Calcular RR Real (Sem manipulação)
                risk = abs(entry_price - stop)
                reward = abs(target - entry_price)
                if risk <= 0:
                    continue
                real_rr = round(reward / risk, 2)

                # 3. HARD GATE DE RR — Rejeitar imediatamente se abaixo do mínimo exigido
                required_rr = max(effective_global_min_rr, playbook.min_rr)
                if real_rr < required_rr:
                    continue  # REJECTED — RR abaixo do exigido pelo Playbook/Global

                # 4. Verificar Obstáculo Imediato (Room to Run)
                obstacle_ahead = False
                if candidate_direction == "long":
                    # Checar se há resistência antes de atingir 1x ATR do alvo
                    near_res = [r for r in result.resistance if entry_price < r < target]
                    if near_res and (near_res[0] - entry_price) < (0.8 * atr):
                        obstacle_ahead = True
                else:
                    near_sup = [s for s in result.support if target < s < entry_price]
                    if near_sup and (entry_price - near_sup[0]) < (0.8 * atr):
                        obstacle_ahead = True

                # 5. Calcular Scores na Arquitetura de 3 Scores
                score = compute_opportunity_score(
                    trend=result.trend,
                    bos=result.structure.bos,
                    choch=result.structure.choch,
                    regime_compatible=True,
                    rr=real_rr,
                    distance_to_zone_pct=distance_pct,
                    volatility_bucket=regime_result.volatility_bucket,
                    btc_context=btc_context,
                    correlation_penalty=False,
                    playbook_stats=None,
                    volume_expansion=ctx["vol_expansion"],
                    rsi_alignment=(result.rsi > 50 if candidate_direction == "long" else result.rsi < 50),
                    obstacle_ahead=obstacle_ahead,
                )

                # Hard Gate de Trade Score: oportunidade precisa de nota consistente
                if score.trade_score < 70.0:
                    continue

                symbol_candidates.append(
                    OpportunityResult(
                        symbol=symbol,
                        direction=candidate_direction,
                        playbook=playbook.name,
                        style=playbook.style,
                        regime=regime_result.regime,
                        btc_context=btc_context,
                        price=price,
                        entry_zone=entry_zone,
                        stop=stop,
                        target=target,
                        rr=real_rr,
                        distance_to_zone_pct=distance_pct,
                        score=score,
                        correlated_with=None,
                        notes=[
                            *eval_res.reasons,
                            *regime_result.notes,
                            f"RR Real: {real_rr} (Mínimo exigido: {required_rr})",
                        ],
                    )
                )
                found_for_symbol = True
                break  # Encontrou o melhor playbook para esta direção

        if symbol_candidates:
            # 6. DIRECTION RESOLUTION ENGINE — Desempate LONG vs SHORT para o mesmo símbolo
            long_cands = [c for c in symbol_candidates if c.direction == "long"]
            short_cands = [c for c in symbol_candidates if c.direction == "short"]

            if long_cands and short_cands:
                best_long = max(long_cands, key=lambda c: c.score.trade_score)
                best_short = max(short_cands, key=lambda c: c.score.trade_score)
                score_diff = best_long.score.trade_score - best_short.score.trade_score

                if score_diff >= 5.0 or (score_diff > 0 and result.trend == "Bullish"):
                    raw_candidates_by_symbol[symbol] = [best_long]
                elif score_diff <= -5.0 or (score_diff < 0 and result.trend == "Bearish"):
                    raw_candidates_by_symbol[symbol] = [best_short]
                else:
                    # Conflito direcional grave / empate em zona de ruído: rejeitar ambas
                    no_edge.append({
                        "symbol": symbol,
                        "regime": regime_result.regime,
                        "reason": "DIRECTION_CONFLICT: Sinais simultâneos de LONG e SHORT com scores equivalentes.",
                    })
            else:
                raw_candidates_by_symbol[symbol] = symbol_candidates
        elif not found_for_symbol:
            no_edge.append({
                "symbol": symbol,
                "regime": regime_result.regime,
                "reason": f"Sem setup qualificado com RR >= {effective_global_min_rr} e Score >= 70 no regime {regime_result.regime}.",
            })

    # Consolidar todos os candidatos aprovados pelos Hard Gates
    candidates: list[OpportunityResult] = []
    for sym_cands in raw_candidates_by_symbol.values():
        candidates.extend(sym_cands)

    # 7. CORRELATED EXPOSURE FILTER & RE-RANKING
    candidates.sort(key=lambda c: c.score.trade_score, reverse=True)


    if len(candidates) > 1 and len(returns_by_symbol) > 1:
        ranked_symbols_in_order = list(dict.fromkeys(c.symbol for c in candidates))
        try:
            correlation_matrix = compute_return_correlation(returns_by_symbol)
            correlation_flags = flag_correlated_duplicates(ranked_symbols_in_order, correlation_matrix, threshold=0.85)
        except Exception:  # noqa: BLE001 - correlação é um refinamento, nunca deve derrubar o ranking inteiro.
            correlation_flags = {}

        rescored: list[OpportunityResult] = []
        for c in candidates:
            correlated_with = correlation_flags.get(c.symbol)
            if correlated_with is None:
                rescored.append(c)
                continue
            new_score = compute_opportunity_score(
                trend="Bullish" if c.direction == "long" else "Bearish",  # já refletido no score original -- aqui só re-penaliza risk/overall
                bos=True,
                choch=False,
                regime_compatible=True,
                rr=c.rr,
                distance_to_zone_pct=c.distance_to_zone_pct,
                volatility_bucket="NORMAL",
                btc_context=c.btc_context,
                correlation_penalty=True,
                playbook_stats=None,
            )
            rescored.append(replace(c, correlated_with=correlated_with, score=new_score))
        candidates = sorted(rescored, key=lambda c: c.score.overall, reverse=True)

    return {
        "timeframe": timeframe,
        "btc_regime": btc_regime.to_dict(),
        "opportunities": [c.to_dict() for c in candidates[:top_n]],
        "no_edge": no_edge,
        "errors": errors,
        "disclaimer": (
            "Ranking pontual (momento da chamada), não monitoramento contínuo. Scores refletem "
            "critérios técnicos atuais, não são probabilidade de lucro. Entry/stop/target são "
            "uma estimativa de primeiro corte a partir de zonas de suporte/resistência -- validar "
            "antes de qualquer execução real."
        ),
    }
