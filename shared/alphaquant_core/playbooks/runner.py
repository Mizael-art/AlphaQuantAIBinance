"""
Runner do Playbook Engine — combina a etapa DATA (compartilhada com o
Data Engine, sem buscar os mesmos candles duas vezes) com o cálculo do
PlaybookContext, a avaliação dos 10 playbooks, o Scoring Engine (Fase 5)
e o Quality Filter (Fase 6), persistindo o resultado em `Opportunity`.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from alphaquant_core.db.models import Opportunity
from alphaquant_core.db.models import Playbook as PlaybookRow
from alphaquant_core.engines.data_engine import MarketDataClient
from alphaquant_core.engines.orchestrator import fetch_and_persist
from alphaquant_core.engines.decision import make_decision
from alphaquant_core.engines.quality_filter import (
    DEFAULT_MINIMUM_RR,
    DEFAULT_MINIMUM_SCORE,
    evaluate_quality,
)
from alphaquant_core.engines.scoring import compute_score
from alphaquant_core.engines.structure import current_regime, find_swings
from alphaquant_core.engines.targets import compute_targets
from alphaquant_core.playbooks.base import PlaybookContext, PlaybookResult
from alphaquant_core.playbooks.engine import build_context, evaluate_all
from alphaquant_core.services.opportunity_service import (
    compute_confidence,
    upsert_future_opportunity,
    upsert_opportunity,
)

# Mapeamento de timeframe de execução -> timeframe maior (HTF) usado pelo
# HTF Continuation (Playbook 8) e pelo Scoring Engine (confirmação HTF).
# "1d" não tem HTF maior configurado (None) — nesse caso htf_regime fica
# sempre None e a confirmação HTF simplesmente não se aplica.
HTF_TIMEFRAME_MAP: dict[str, str | None] = {
    "15m": "4h",
    "1h": "4h",
    "4h": "1d",
    "1d": None,
}


def htf_timeframe_for(timeframe: str) -> str | None:
    return HTF_TIMEFRAME_MAP.get(timeframe)


def compute_htf_regime(
    db: Session,
    symbol: str,
    htf_timeframe: str | None,
    client: MarketDataClient | None = None,
    limit: int = 200,
) -> str | None:
    """
    Calcula o regime de estrutura num timeframe maior — mais leve que
    `scan_symbol` (não roda indicadores/liquidez/playbooks, só o
    suficiente para `current_regime`). Levanta BinanceRequestError se a
    coleta falhar, igual a qualquer chamada do Data Engine.
    """
    if htf_timeframe is None:
        return None
    df, _candles, _stored = fetch_and_persist(db, symbol, htf_timeframe, client=client, limit=limit)
    swings = find_swings(df)
    return current_regime(swings)


def scan_symbol(
    db: Session,
    symbol: str,
    timeframe: str,
    client: MarketDataClient | None = None,
    limit: int = 200,
    htf_regime: str | None = None,
) -> tuple[PlaybookContext, list[PlaybookResult]]:
    """
    Ciclo Data -> Playbooks para um asset/timeframe. Levanta
    BinanceRequestError se a coleta falhar (mesmo contrato do Data Engine
    — quem chama decide como registrar/retry).
    """
    df, _candles, _stored = fetch_and_persist(db, symbol, timeframe, client=client, limit=limit)
    ctx = build_context(symbol, timeframe, df, htf_regime=htf_regime)
    results = evaluate_all(ctx)
    return ctx, results


def _playbook_thresholds(db: Session, playbook_name: str) -> tuple[float, float]:
    """
    Lê minimum_score/minimum_rr da tabela `playbooks` (seed da Fase 4).
    Cai nos padrões (70/2) se o playbook não estiver cadastrado — nunca
    quebra o ciclo do Worker por um cadastro ausente.
    """
    row = db.query(PlaybookRow).filter_by(name=playbook_name).one_or_none()
    if row is None:
        return DEFAULT_MINIMUM_SCORE, DEFAULT_MINIMUM_RR
    return float(row.minimum_score), float(row.minimum_rr)


def scan_and_score(
    db: Session,
    symbol: str,
    timeframe: str,
    client: MarketDataClient | None = None,
    limit: int = 200,
    htf_regime: str | None = None,
) -> tuple[PlaybookContext, list[PlaybookResult], list[Opportunity]]:
    """
    Ciclo completo Data -> Playbooks -> Targets -> Score -> Quality Filter
    -> Decision Engine -> persistência (Fases 3-7 e 11 — o pipeline
    principal da seção 68 fica fechado ponta a ponta aqui). Playbooks com
    `matched=True` passam pelo pipeline completo (Quality Filter +
    Decision Engine); playbooks com `matched=False` mas `progress>0` e
    direção definida viram Future Opportunity (Fase 11, `status=
    FORMATION`, sem Quality Filter/Decision Engine — ver
    `upsert_future_opportunity`). `Opportunity.status`/`.decision` para
    o caminho confirmado refletem o resultado real do Decision Engine:
    `CONFIRMED` se ENTRAR, `FORMATION` se ESPERAR, `INVALIDATED` se
    REPROVAR.
    """
    ctx, results = scan_symbol(db, symbol, timeframe, client=client, limit=limit, htf_regime=htf_regime)

    opportunities: list[Opportunity] = []
    for result in results:
        if result.matched:
            target_result = compute_targets(ctx.swings, result.direction, result.entry, result.stop)
            score_result = compute_score(ctx, result, target_result)
            confidence = compute_confidence(ctx)
            minimum_score, minimum_rr = _playbook_thresholds(db, result.playbook)
            quality_result = evaluate_quality(
                result, target_result, score_result, confidence,
                minimum_score=minimum_score, minimum_rr=minimum_rr,
            )
            decision_result = make_decision(quality_result, confidence)
            opportunity = upsert_opportunity(
                db, ctx, result, target_result, score_result, quality_result, decision_result,
            )
            opportunities.append(opportunity)
        else:
            score_result = compute_score(ctx, result, None)
            future_opportunity = upsert_future_opportunity(db, ctx, result, score_result)
            if future_opportunity is not None:
                opportunities.append(future_opportunity)

    return ctx, results, opportunities
