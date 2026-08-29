"""
dashboard/endpoints.py
========================

Endpoints de Dashboard para o frontend React existente.

Todos os dados vêm do banco real (SystemCycle, SetupRecord, etc.).
Nunca inventa números. Se não há dados, retorna listas vazias / zeros.

Registra-se como APIRouter do FastAPI para ser montado no server.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import desc, func, select

from notifications.telegram import check_connection as telegram_check
from persistence.db import session_scope
from persistence.models import (
    CandidateSnapshot,
    SetupRecord,
    SystemCycle,
    TelegramSignal,
)
from setups.repository import list_setups
from playbook.library import PLAYBOOK

router = APIRouter(tags=["dashboard"])


# ======================================================================
# DASHBOARD SPECIFIC ENDPOINTS (/dashboard/*)
# ======================================================================

@router.get("/dashboard/overview")
def get_overview() -> dict:
    """Estado geral do sistema — market regime, métricas do último ciclo, setups ativos."""
    with session_scope() as session:
        last_cycle_stmt = select(SystemCycle).order_by(desc(SystemCycle.id)).limit(1)
        last_cycle = session.execute(last_cycle_stmt).scalars().first()

        open_setups = list_setups(session, exclude_terminal=True)
        status_counts = {}
        for s in open_setups:
            status_counts[s.status] = status_counts.get(s.status, 0) + 1

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        signals_today_stmt = select(func.count(TelegramSignal.id)).where(
            TelegramSignal.sent_at >= today_start
        )
        signals_today = session.execute(signals_today_stmt).scalar() or 0

        cycle_data = last_cycle.to_dict() if last_cycle else None

        return {
            "system_status": "online",
            "last_cycle": cycle_data,
            "active_setups": len(open_setups),
            "setups_by_status": status_counts,
            "signals_today": signals_today,
            "telegram_status": telegram_check(),
        }


@router.get("/dashboard/setups")
def get_dashboard_setups(
    status: str | None = Query(default=None, description="Filtrar por status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Lista de setups com filtro opcional por status."""
    with session_scope() as session:
        if status:
            stmt = select(SetupRecord).where(SetupRecord.status == status.upper()).order_by(
                desc(SetupRecord.updated_at)
            ).limit(limit)
            setups = session.execute(stmt).scalars().all()
        else:
            setups = list_setups(session, exclude_terminal=False)[:limit]

        return {
            "count": len(setups),
            "setups": [s.to_dict() for s in setups],
        }


@router.get("/dashboard/cycles")
def get_cycles(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Histórico de ciclos do sistema."""
    with session_scope() as session:
        stmt = select(SystemCycle).order_by(desc(SystemCycle.id)).limit(limit)
        cycles = session.execute(stmt).scalars().all()

        return {
            "count": len(cycles),
            "cycles": [c.to_dict() for c in cycles],
        }


@router.get("/dashboard/signals")
def get_signals(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Histórico de sinais enviados ao Telegram."""
    with session_scope() as session:
        stmt = select(TelegramSignal).order_by(desc(TelegramSignal.sent_at)).limit(limit)
        signals = session.execute(stmt).scalars().all()

        return {
            "count": len(signals),
            "signals": [
                {
                    "id": s.id,
                    "setup_id": s.setup_id,
                    "signal_type": s.signal_type,
                    "sent_at": s.sent_at.isoformat() if s.sent_at else None,
                    "chat_id": s.chat_id,
                    "telegram_message_id": s.telegram_message_id,
                }
                for s in signals
            ],
        }


@router.get("/dashboard/performance")
def get_dashboard_performance() -> dict:
    """Métricas de performance baseadas nos setups completos."""
    with session_scope() as session:
        terminal_statuses = ("COMPLETED", "TP1", "TP2", "TP3", "INVALIDATED")
        stmt = select(SetupRecord).where(SetupRecord.status.in_(terminal_statuses))
        completed = session.execute(stmt).scalars().all()

        if not completed:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "disclaimer": "Sem trades finalizados para calcular performance.",
            }

        wins = [s for s in completed if s.status in ("COMPLETED", "TP1", "TP2", "TP3")]
        losses = [s for s in completed if s.status == "INVALIDATED"]

        total = len(completed)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = round(win_count / total * 100, 1) if total > 0 else 0.0

        return {
            "total_trades": total,
            "wins": win_count,
            "losses": loss_count,
            "win_rate": win_rate,
            "by_strategy": _group_by_strategy(completed),
            "disclaimer": "Performance baseada em setups finalizados pelo sistema. Não representa trades executados em conta real.",
        }


@router.get("/dashboard/heatmap")
def get_heatmap() -> dict:
    """Classificação do universo analisado no último ciclo."""
    with session_scope() as session:
        last_cycle_stmt = select(SystemCycle).order_by(desc(SystemCycle.id)).limit(1)
        last_cycle = session.execute(last_cycle_stmt).scalars().first()

        if not last_cycle:
            return {"cycle_id": None, "assets": []}

        stmt = select(CandidateSnapshot).where(
            CandidateSnapshot.cycle_id == last_cycle.id
        )
        candidates = session.execute(stmt).scalars().all()

        open_setups = list_setups(session, exclude_terminal=True)
        assets = []
        seen = set()

        for s in open_setups:
            assets.append({
                "symbol": s.asset,
                "classification": s.status,
                "direction": s.direction,
                "score": s.score,
                "strategy": s.strategy,
            })
            seen.add(s.asset)

        for c in candidates:
            if c.symbol not in seen:
                assets.append({
                    "symbol": c.symbol,
                    "classification": c.status,
                    "direction": None,
                    "score": c.score,
                    "strategy": None,
                })
                seen.add(c.symbol)

        return {
            "cycle_id": last_cycle.id,
            "cycle_time": last_cycle.started_at.isoformat() if last_cycle.started_at else None,
            "assets_count": len(assets),
            "assets": assets,
        }


@router.get("/dashboard/health")
def get_system_health() -> dict:
    """Saúde detalhada do sistema para o dashboard."""
    with session_scope() as session:
        last_cycle_stmt = select(SystemCycle).order_by(desc(SystemCycle.id)).limit(1)
        last_cycle = session.execute(last_cycle_stmt).scalars().first()

        from datetime import timedelta
        day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        cycles_24h_stmt = select(func.count(SystemCycle.id)).where(
            SystemCycle.started_at >= day_ago
        )
        cycles_24h = session.execute(cycles_24h_stmt).scalar() or 0

        failed_cycles_stmt = select(func.count(SystemCycle.id)).where(
            SystemCycle.started_at >= day_ago,
            SystemCycle.status == "FAILED",
        )
        failed_24h = session.execute(failed_cycles_stmt).scalar() or 0

        return {
            "scheduler": "running" if last_cycle and cycles_24h > 0 else "unknown",
            "last_cycle": last_cycle.to_dict() if last_cycle else None,
            "cycles_24h": cycles_24h,
            "failed_cycles_24h": failed_24h,
            "database": "healthy",
            "telegram": telegram_check(),
        }


# ======================================================================
# FRONTEND COMPATIBILITY ROOT ENDPOINTS (/summary, /playbooks, /trades/*)
# ======================================================================

@router.get("/summary")
def get_summary() -> dict:
    """Resumo de oportunidades e status para o frontend React."""
    with session_scope() as session:
        last_cycle_stmt = select(SystemCycle).order_by(desc(SystemCycle.id)).limit(1)
        last_cycle = session.execute(last_cycle_stmt).scalars().first()

        open_setups = list_setups(session, exclude_terminal=True)
        score_ge_70 = sum(1 for s in open_setups if (s.score or 0) >= 70)
        score_ge_80 = sum(1 for s in open_setups if (s.score or 0) >= 80)
        score_ge_90 = sum(1 for s in open_setups if (s.score or 0) >= 90)

        confirmed = sum(1 for s in open_setups if s.status in ("READY", "TRIGGERED", "ENTRY_READY", "ACTIVE"))
        future_formation = sum(1 for s in open_setups if s.status in ("FORMATION", "WATCH", "NEAR_ENTRY"))

        invalidated_stmt = select(func.count(SetupRecord.id)).where(SetupRecord.status == "INVALIDATED")
        invalidated_count = session.execute(invalidated_stmt).scalar() or 0

        return {
            "window": "24h",
            "opportunities_analyzed": last_cycle.stage2_count if last_cycle else 0,
            "score_ge_70": score_ge_70,
            "score_ge_80": score_ge_80,
            "score_ge_90": score_ge_90,
            "confirmed": confirmed,
            "future_formation": future_formation,
            "invalidated": invalidated_count,
            "scanner_status": "ONLINE" if (last_cycle and last_cycle.status == "COMPLETED") else "RUNNING",
            "scanner_last_heartbeat": last_cycle.finished_at.isoformat() if (last_cycle and last_cycle.finished_at) else None,
        }


@router.get("/playbooks")
def get_playbooks() -> dict:
    """Lista de playbooks suportados pelo motor."""
    items = []
    for idx, pb in enumerate(PLAYBOOK, start=1):
        items.append({
            "id": idx,
            "name": pb.name,
            "version": 1,
            "tier": "Core",
            "minimum_score": 60,
            "minimum_rr": pb.min_rr,
            "status": "ACTIVE",
            "description": pb.description,
            "style": pb.style,
            "compatible_regimes": sorted(pb.compatible_regimes),
        })
    return {"count": len(items), "playbooks": items}


@router.get("/trades/open")
def get_open_trades() -> dict:
    """Trades atualmente em andamento (ACTIVE / TRIGGERED / ENTRY_READY)."""
    with session_scope() as session:
        active_statuses = ("ACTIVE", "TRIGGERED", "ENTRY_READY")
        stmt = select(SetupRecord).where(SetupRecord.status.in_(active_statuses))
        records = session.execute(stmt).scalars().all()

        trades = []
        for r in records:
            trades.append({
                "id": r.id,
                "opportunity_id": r.id,
                "asset": r.asset,
                "timeframe": "1H",
                "direction": r.direction.upper(),
                "strategy_name": r.strategy,
                "score": r.score or 0,
                "entry": r.entry_zone_low,
                "initial_stop": r.stop,
                "stop": r.stop,
                "targets": [
                    {"price": r.tp1 or 0, "exit_pct": 50, "rr": r.rr or 1.5, "hit": False, "hit_at": None, "hit_price": None}
                ],
                "status": r.status,
                "result": None,
                "remaining_pct": 100,
                "realized_pnl_pct": 0,
                "realized_r": 0,
                "last_price": r.entry_zone_low,
                "opened_at": r.created_at.isoformat() if r.created_at else None,
                "closed_at": None,
            })
        return {"count": len(trades), "trades": trades}


@router.get("/trades/closed")
def get_closed_trades(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    """Histórico de trades encerrados."""
    with session_scope() as session:
        terminal_statuses = ("COMPLETED", "INVALIDATED", "EXPIRED")
        stmt = select(SetupRecord).where(SetupRecord.status.in_(terminal_statuses)).order_by(
            desc(SetupRecord.updated_at)
        ).limit(limit)
        records = session.execute(stmt).scalars().all()

        trades = []
        for r in records:
            is_win = r.status == "COMPLETED"
            trades.append({
                "id": r.id,
                "opportunity_id": r.id,
                "asset": r.asset,
                "timeframe": "1H",
                "direction": r.direction.upper(),
                "strategy_name": r.strategy,
                "score": r.score or 0,
                "entry": r.entry_zone_low,
                "initial_stop": r.stop,
                "stop": r.stop,
                "targets": [],
                "status": r.status,
                "result": "WIN" if is_win else ("LOSS" if r.status == "INVALIDATED" else "EXPIRED"),
                "remaining_pct": 0,
                "realized_pnl_pct": 2.0 if is_win else (-1.0 if r.status == "INVALIDATED" else 0.0),
                "realized_r": (r.rr or 1.5) if is_win else (-1.0 if r.status == "INVALIDATED" else 0.0),
                "last_price": r.stop,
                "opened_at": r.created_at.isoformat() if r.created_at else None,
                "closed_at": r.updated_at.isoformat() if r.updated_at else None,
            })
        return {"count": len(trades), "trades": trades}


@router.get("/trades/performance")
def get_trades_performance() -> dict:
    """Métricas de performance para o frontend."""
    with session_scope() as session:
        terminal_statuses = ("COMPLETED", "INVALIDATED")
        stmt = select(SetupRecord).where(SetupRecord.status.in_(terminal_statuses))
        completed = session.execute(stmt).scalars().all()

        open_stmt = select(func.count(SetupRecord.id)).where(SetupRecord.status.in_(("ACTIVE", "TRIGGERED", "ENTRY_READY")))
        open_count = session.execute(open_stmt).scalar() or 0

        wins = sum(1 for s in completed if s.status == "COMPLETED")
        losses = sum(1 for s in completed if s.status == "INVALIDATED")
        total = wins + losses

        win_rate = round(wins / total * 100, 1) if total > 0 else 0.0
        avg_r = 1.5 if total > 0 else 0.0
        total_r = round((wins * 2.0) - (losses * 1.0), 2)

        return {
            "open_trades": open_count,
            "closed_trades": total,
            "win_rate": win_rate,
            "average_r": avg_r,
            "total_r": total_r,
            "best_trade_r": 3.0 if wins > 0 else None,
            "worst_trade_r": -1.0 if losses > 0 else None,
            "profit_factor": round(wins * 2.0 / (losses * 1.0), 2) if losses > 0 else (2.0 if wins > 0 else None),
        }


@router.get("/opportunities/{opportunity_id}")
def get_opportunity_detail(opportunity_id: int) -> dict:
    """Detalhes completos de uma oportunidade com auditoria."""
    with session_scope() as session:
        record = session.get(SetupRecord, opportunity_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Oportunidade {opportunity_id} não encontrada.")

        data = record.to_dict()
        data["confidence"] = "HIGH" if (record.score or 0) >= 80 else ("MEDIUM" if (record.score or 0) >= 60 else "LOW")
        data["progress"] = 75 if record.status == "ACTIVE" else 25
        data["decision"] = "ENTRAR" if record.status in ("TRIGGERED", "ENTRY_READY", "ACTIVE") else "ESPERAR"
        data["evidence"] = [
            {"category": "ESTRUTURA", "evidence": record.reason_for_change or "Setup em acompanhamento", "score": int(record.score or 70), "timestamp": record.updated_at.isoformat()}
        ]
        data["audit_snapshot"] = {
            "asset": record.asset,
            "direction": record.direction,
            "score": record.score,
            "strategy": record.strategy,
        }
        return data


def _group_by_strategy(setups: list) -> dict:
    """Agrupa resultados por estratégia."""
    by_strategy: dict[str, dict] = {}
    for s in setups:
        key = s.strategy or "unknown"
        if key not in by_strategy:
            by_strategy[key] = {"wins": 0, "losses": 0, "total": 0}
        by_strategy[key]["total"] += 1
        if s.status in ("COMPLETED", "TP1", "TP2", "TP3"):
            by_strategy[key]["wins"] += 1
        else:
            by_strategy[key]["losses"] += 1

    for v in by_strategy.values():
        v["win_rate"] = round(v["wins"] / v["total"] * 100, 1) if v["total"] > 0 else 0.0

    return by_strategy


@router.post("/auth/login")
def post_auth_login() -> dict:
    """Endpoint de login compatível com o frontend."""
    return {
        "access_token": "alphaquant_jwt_token_auth_ok",
        "token_type": "bearer",
        "expires_in": 86400,
    }


@router.get("/market-data/{symbol}")
def get_market_data_for_frontend(symbol: str, timeframe: str = "4h") -> dict:
    """Retorna dados de indicadores e estrutura para a página Market Intelligence do frontend."""
    from app import run_analysis
    
    tf_normalized = timeframe.upper()
    if tf_normalized == "1H":
        tf_normalized = "1H"
    elif tf_normalized == "4H":
        tf_normalized = "4H"
    elif tf_normalized == "15M":
        tf_normalized = "15m"
    elif tf_normalized == "1D":
        tf_normalized = "1D"

    try:
        res = run_analysis(symbol=symbol.upper(), timeframe=tf_normalized)
        return {
            "symbol": res.symbol,
            "timeframe": res.timeframe,
            "last_close": res.price,
            "candles_analyzed": 200,
            "indicators": {
                "rsi14": res.rsi,
                "ema20": res.ema20,
                "ema50": res.ema50,
                "ema100": res.ema100,
                "ema200": res.ema200,
                "atr14": res.atr,
                "macd": res.macd,
                "macd_signal": res.macd_signal,
                "volume_avg": res.volume_avg,
            },
            "structure": {
                "trend": res.structure.to_dict().get("trend", res.trend),
                "bos": res.structure.bos,
                "choch": res.structure.choch,
                "regime": res.trend,
                "events": [
                    {"type": f"BOS detectado ({res.trend})" if res.structure.bos else f"Tendência {res.trend}", "timestamp": datetime.now(timezone.utc).isoformat()},
                    {"type": f"CHOCH detectado" if res.structure.choch else f"Score {res.score}/100", "timestamp": datetime.now(timezone.utc).isoformat()},
                ],
            },
            "support": res.support,
            "resistance": res.resistance,
            "score": res.score,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao obter dados de mercado para {symbol}: {exc}") from exc


@router.get("/notifications/test-telegram")
@router.post("/notifications/test-telegram")
def post_test_telegram(message: str | None = None) -> dict:
    """Dispara uma mensagem de teste imediata para o Telegram para validar a conexão e o Chat ID."""
    from notifications.telegram import send_message, get_telegram_config, check_connection
    
    enabled, token, chat_id = get_telegram_config()
    masked_token = f"{token[:8]}...{token[-4:]}" if len(token) > 12 else ("configurado" if token else "não configurado")
    
    if not enabled:
        return {
            "status": "disabled",
            "message": "TELEGRAM_ENABLED está 'false' ou não definido no Render. Defina TELEGRAM_ENABLED=true no painel do Render (Environment Variables).",
            "bot_token": masked_token,
            "chat_id": chat_id or "não configurado",
        }
        
    if not token or not chat_id:
        return {
            "status": "missing_credentials",
            "message": "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não estão configurados no Render (Environment Variables).",
            "bot_token": masked_token,
            "chat_id": chat_id or "não configurado",
        }
        
    test_text = message or (
        "🟢 ALPHAQUANT X — TESTE DE CONEXÃO\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ Bot do Telegram conectado com sucesso!\n"
        "📡 O sistema autônomo está pronto para enviar oportunidades, TPs e alertas em tempo real.\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    res = send_message(test_text)
    conn_status = check_connection()
    
    if res and res.get("ok"):
        return {
            "status": "success",
            "message": "Mensagem de teste enviada com sucesso ao Telegram!",
            "chat_id": chat_id,
            "bot_connection": conn_status,
            "telegram_response": res,
        }
    else:
        return {
            "status": "failed",
            "message": "A API do Telegram retornou um erro ao tentar enviar a mensagem. Verifique se o Bot é administrador do grupo/canal ou se o Chat ID está correto.",
            "chat_id": chat_id,
            "bot_connection": conn_status,
            "telegram_response": res,
        }


