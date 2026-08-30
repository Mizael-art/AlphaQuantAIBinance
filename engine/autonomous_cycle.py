"""
engine/autonomous_cycle.py
============================

Pipeline completo do ciclo autônomo de mercado.

Ordem de execução (conforme especificação do usuário):
  1. Monitorar setups ativos (reutiliza monitoring/service.py)
  2. Atualizar universo Bybit
  3. Stage 1 Fast Scan + Stage 2 Deep Analysis (reutiliza scanner/screener.py)
  4. Discovery / Ranking (reutiliza discovery/engine.py)
  5. Para cada oportunidade: Risk Engine → Decision Engine → Setup Upsert
  6. Persistir métricas do ciclo

Nenhum módulo de análise é reescrito — apenas orquestrado.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from config import (
    DEFAULT_SCAN_HTF,
    DEFAULT_SCAN_LTF,
    SCAN_STAGE1_MIN_TURNOVER_USDT,
    SCAN_STAGE1_TOP_N,
)
from decision.engine import evaluate_decision
from discovery.engine import scan_opportunities
from engine.cache import GlobalKlineCache, enable_market_data_cache
from monitoring.service import run_monitoring_cycle
from persistence.db import session_scope
from persistence.models import CandidateSnapshot, SystemCycle
from providers.bybit_universe import get_all_bybit_usdt_perpetuals
from risk.engine import ProposedTrade, evaluate_trade_risk
from risk.repository import build_risk_limits, build_risk_state, get_or_create_account
from notifications.engine import process_monitoring_updates, process_new_setup
from scanner.screener import scan_universe
from setups.lifecycle import WATCH
from setups.memory import upsert_setup
from setups.schema import EntryZone, SetupCandidate

logger = logging.getLogger("alphaquant.engine.cycle")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _determine_entry_quality(distance_pct: float | None) -> str:
    """Mapeia distância percentual para qualidade de entrada do Decision Engine."""
    if distance_pct is None:
        return "NO_ENTRY"
    if distance_pct < 0.2:
        return "ENTRY_NOW"
    if distance_pct < 1.0:
        return "ENTRY_ON_PULLBACK"
    if distance_pct < 2.0:
        return "ENTRY_ON_CONFIRMATION"
    return "NO_ENTRY"


def _execute_pipeline(session: Session, cycle: SystemCycle) -> None:
    """Pipeline interno — todas as exceções por ativo são capturadas
    individualmente para não derrubar o ciclo inteiro."""

    # ──────────────────────────────────────────────────────────────────
    # 1. Habilitar cache de klines para este ciclo
    # ──────────────────────────────────────────────────────────────────
    enable_market_data_cache()
    GlobalKlineCache.clear()

    # ──────────────────────────────────────────────────────────────────
    # 2. MONITORING — atualizar setups existentes (TP/SL/expiração)
    # ──────────────────────────────────────────────────────────────────
    try:
        mon_result = run_monitoring_cycle(session)
        cycle.setups_expired = len(mon_result.expired)
        # Contar invalidados a partir dos updates
        cycle.setups_invalidated = sum(
            1 for u in mon_result.updated if u.get("to") == "INVALIDATED"
        )
        if mon_result.errors:
            cycle.errors_count += len(mon_result.errors)
            cycle.error_summary["monitoring_errors"] = mon_result.errors
        logger.info(
            f"[MONITORING] Checked: {mon_result.checked} | "
            f"Updated: {len(mon_result.updated)} | "
            f"Expired: {len(mon_result.expired)}"
        )
        # Processar notificações Telegram para eventos do monitoring (TP, stop, invalidação)
        if mon_result.updated:
            try:
                mon_signals = process_monitoring_updates(session, mon_result.updated)
                cycle.signals_sent += mon_signals
            except Exception as exc:
                logger.error(f"Erro ao processar notificações do monitoring: {exc}")
    except Exception as exc:
        logger.error(f"Erro durante monitoramento de setups: {exc}")
        cycle.error_summary["monitoring_fatal"] = str(exc)
        cycle.errors_count += 1

    # ──────────────────────────────────────────────────────────────────
    # 3. UNIVERSE DISCOVERY
    # ──────────────────────────────────────────────────────────────────
    try:
        universe = get_all_bybit_usdt_perpetuals()
        cycle.universe_size = len(universe)
        logger.info(f"[UNIVERSE] {len(universe)} perpétuos USDT descobertos.")
    except Exception as exc:
        logger.error(f"Falha ao buscar universo Bybit: {exc}")
        cycle.error_summary["universe_error"] = str(exc)
        cycle.errors_count += 1
        return  # Sem universo, não há como prosseguir

    # ──────────────────────────────────────────────────────────────────
    # 4. STAGE 1 (Fast Filter) + STAGE 2 (Deep Analysis)
    # ──────────────────────────────────────────────────────────────────
    try:
        scan_result = scan_universe(
            htf=DEFAULT_SCAN_HTF,
            ltf=DEFAULT_SCAN_LTF,
            top_n=SCAN_STAGE1_TOP_N,
            min_turnover_usdt=SCAN_STAGE1_MIN_TURNOVER_USDT,
            include_out_of_zone=True,
        )
        cycle.stage1_count = scan_result.stage1_candidates
        cycle.stage2_count = scan_result.symbols_analyzed
        logger.info(
            f"[SCAN] Stage1: {scan_result.stage1_candidates} | "
            f"Stage2 analyzed: {scan_result.symbols_analyzed} | "
            f"Entry Zone: {len(scan_result.entry_zone)} | "
            f"Watch: {len(scan_result.watch)} | "
            f"Out of Zone: {len(scan_result.out_of_zone)} | "
            f"Errors: {len(scan_result.errors)}"
        )

        # Registrar erros do scan
        if scan_result.errors:
            cycle.errors_count += len(scan_result.errors)
            cycle.error_summary["scan_errors"] = scan_result.errors

        # Registrar candidatos fora de zona para auditoria
        for out in scan_result.out_of_zone:
            session.add(CandidateSnapshot(
                cycle_id=cycle.id,
                symbol=out.symbol,
                stage="stage2",
                score=out.score_htf,
                status="fora_de_zona",
                rejection_reason=out.note or "Trend conflict ou score insuficiente",
            ))

    except Exception as exc:
        logger.error(f"Falha durante Stage 1/2: {exc}")
        cycle.error_summary["scan_fatal"] = str(exc)
        cycle.errors_count += 1
        return

    # Reunir candidatos para Discovery
    candidatos = (
        [e.symbol for e in scan_result.entry_zone]
        + [w.symbol for w in scan_result.watch]
    )
    if not candidatos:
        logger.info("[DISCOVERY] Nenhum candidato em entry/watch. Pipeline encerrado.")
        return

    # ──────────────────────────────────────────────────────────────────
    # 5. DISCOVERY / RANKING + PLAYBOOK VALIDATION
    # ──────────────────────────────────────────────────────────────────
    try:
        discovery_res = scan_opportunities(
            symbols=candidatos,
            timeframe=DEFAULT_SCAN_LTF,
            top_n=20,  # Pegar mais candidatos para alimentar risk/decision
        )
        opportunities = discovery_res.get("opportunities", [])
        no_edge = discovery_res.get("no_edge", [])
        disc_errors = discovery_res.get("errors", {})

        cycle.discovery_count = len(candidatos)
        cycle.playbook_valid_count = len(opportunities)

        if disc_errors:
            cycle.errors_count += len(disc_errors)
            cycle.error_summary["discovery_errors"] = disc_errors

        # Registrar sem-edge para auditoria
        for ne in no_edge:
            session.add(CandidateSnapshot(
                cycle_id=cycle.id,
                symbol=ne["symbol"],
                stage="discovery",
                status="no_edge",
                rejection_reason=ne.get("reason", "Sem playbook compatível"),
            ))

        logger.info(
            f"[DISCOVERY] Candidates: {len(candidatos)} | "
            f"Opportunities: {len(opportunities)} | "
            f"No Edge: {len(no_edge)} | "
            f"Errors: {len(disc_errors)}"
        )

    except Exception as exc:
        logger.error(f"Falha durante Discovery: {exc}")
        cycle.error_summary["discovery_fatal"] = str(exc)
        cycle.errors_count += 1
        return

    if not opportunities:
        logger.info("[PIPELINE] Sem oportunidades após Discovery. Pipeline encerrado.")
        return

    # ──────────────────────────────────────────────────────────────────
    # 6. RISK ENGINE + DECISION ENGINE + SETUP UPSERT
    # ──────────────────────────────────────────────────────────────────
    # Buscar conta de risco (ou criar se não existe)
    try:
        account = get_or_create_account(session, "default", starting_capital=10000.0)
    except Exception as exc:
        logger.error(f"Falha ao obter conta de risco: {exc}")
        cycle.error_summary["account_error"] = str(exc)
        cycle.errors_count += 1
        return

    risk_limits = build_risk_limits(account)

    for opp in opportunities:
        symbol = opp.get("symbol", "UNKNOWN")
        try:
            direction = opp["direction"]
            corr_group = opp.get("correlated_with")

            # Risk Engine
            risk_state = build_risk_state(session, account, correlation_group=corr_group)
            trade = ProposedTrade(
                asset=symbol,
                direction=direction,
                requested_risk_pct=1.0,  # Default 1% — respeita config da conta
                correlation_group=corr_group,
            )
            risk_result = evaluate_trade_risk(trade, risk_state, risk_limits)

            # Decision Engine
            entry_quality = _determine_entry_quality(opp.get("distance_to_zone_pct"))
            decision = evaluate_decision(
                direction=direction,
                overall_score=opp.get("overall", opp.get("score", {}).get("overall", 0)),
                risk_decision=risk_result.decision,
                setup_status="UNKNOWN",
                entry_quality=entry_quality,
            )

            # Se rejeitado estritamente pelo Risk Engine por limites de conta
            if risk_result.decision == "REJECTED":
                session.add(CandidateSnapshot(
                    cycle_id=cycle.id,
                    symbol=symbol,
                    stage="risk",
                    score=opp.get("overall", opp.get("score", {}).get("overall")),
                    status="REJECTED",
                    rejection_reason="; ".join(risk_result.reasons),
                ))
                continue

            cycle.quality_valid_count += 1

            # Determinar status inicial do setup (WATCH se aguardando, READY se entrada imediata)
            initial_status = "READY" if decision.decision in ("LONG_NOW", "SHORT_NOW") else WATCH

            # Construir SetupCandidate para upsert
            entry_zone_data = opp.get("entry_zone")
            entry_zone_obj = None
            if entry_zone_data and isinstance(entry_zone_data, dict):
                entry_zone_obj = EntryZone(
                    low=entry_zone_data["low"],
                    high=entry_zone_data["high"],
                )

            candidate = SetupCandidate(
                asset=symbol,
                direction=direction,
                strategy=opp.get("playbook", "unknown"),
                status=initial_status,
                entry_zone=entry_zone_obj,
                stop=opp.get("stop"),
                tp1=opp.get("target"),
                rr=opp.get("rr"),
                score=opp.get("overall", opp.get("score", {}).get("overall")),
                reason=f"Auto-discovery | Decision: {decision.decision} | Conviction: {decision.conviction}",
            )

            upsert_res = upsert_setup(session, candidate)
            if upsert_res.created:
                cycle.setups_created += 1
                logger.info(f"[SETUP NEW] {symbol} {direction} ({initial_status}) via {opp.get('playbook')}")
                # Notificar Telegram apenas para decisões de entrada confirmadas
                if decision.decision in ("LONG_NOW", "SHORT_NOW"):
                    try:
                        sent = process_new_setup(session, upsert_res.record, decision.to_dict())
                        if sent:
                            cycle.signals_sent += 1
                    except Exception as exc:
                        logger.error(f"Erro ao enviar notificação para {symbol}: {exc}")
            elif upsert_res.change_type != "unchanged":
                cycle.setups_updated += 1
                logger.info(f"[SETUP UPDATE] {symbol} {direction} → {upsert_res.change_type}")

        except Exception as exc:
            logger.error(f"Erro ao processar {symbol}: {exc}")
            cycle.errors_count += 1
            cycle.error_summary[f"process_{symbol}"] = str(exc)

    session.flush()


def run_market_cycle() -> None:
    """
    Função pública de entrada — pode ser invocada pelo scheduler,
    pelo endpoint HTTP, ou manualmente para testes.
    
    O caller (scheduler, HTTP, script) NÃO precisa saber nada sobre
    a implementação interna.
    """
    with session_scope() as session:
        cycle = SystemCycle(
            started_at=_utcnow(),
            status="RUNNING",
            error_summary={},
        )
        session.add(cycle)
        session.flush()  # Gera cycle.id para uso nos CandidateSnapshots

        start_time = time.time()
        try:
            _execute_pipeline(session, cycle)
            if cycle.errors_count > 0 and cycle.stage2_count > 0:
                cycle.status = "PARTIAL"
            else:
                cycle.status = "COMPLETED"
        except Exception as exc:
            logger.exception("Falha fatal no ciclo autônomo.")
            cycle.status = "FAILED"
            cycle.error_summary["fatal_error"] = str(exc)
        finally:
            GlobalKlineCache.clear()
            cycle.finished_at = _utcnow()
            cycle.duration_seconds = round(time.time() - start_time, 2)

            logger.info(
                "\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "ALPHAQUANT X — MARKET CYCLE\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"Cycle: #{cycle.id}\n"
                f"Duration: {cycle.duration_seconds}s\n"
                f"Status: {cycle.status}\n"
                f"\n"
                f"MARKET\n"
                f"  Universe: {cycle.universe_size}\n"
                f"\n"
                f"STAGE 1\n"
                f"  Candidates: {cycle.stage1_count}\n"
                f"\n"
                f"STAGE 2\n"
                f"  Deep Analysis: {cycle.stage2_count}\n"
                f"\n"
                f"DISCOVERY\n"
                f"  Candidates: {cycle.discovery_count}\n"
                f"  Playbook Valid: {cycle.playbook_valid_count}\n"
                f"  Quality Valid: {cycle.quality_valid_count}\n"
                f"\n"
                f"SETUPS\n"
                f"  New: +{cycle.setups_created}\n"
                f"  Updated: {cycle.setups_updated}\n"
                f"  Expired: {cycle.setups_expired}\n"
                f"  Invalidated: {cycle.setups_invalidated}\n"
                f"\n"
                f"ERRORS: {cycle.errors_count}\n"
                f"\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
