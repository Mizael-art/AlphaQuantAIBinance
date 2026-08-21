"""
Formatação das mensagens Telegram (seções 16-18 do master prompt).

Cada template usa exclusivamente dados reais já calculados e persistidos
(Score, RR, targets, conditions_met/missing, decision) — nunca um valor
de exemplo ou inventado. Os templates da especificação original são
ilustrativos ("os valores acima são apenas formato de exemplo"); aqui
cada campo é preenchido com o que o sistema efetivamente sabe.
"""
from __future__ import annotations

from datetime import datetime, timezone

from alphaquant_core.db.models import Opportunity

SEPARATOR = "━━━━━━━━━━━━━━━━━━"


def _confidence_label(confidence: str) -> str:
    return {"BAIXA": "BAIXA", "MODERADA": "MODERADA", "ALTA": "ALTA"}.get(confidence, confidence)


def format_signal_message(opportunity: Opportunity) -> str:
    snapshot = opportunity.audit_snapshot or {}
    conditions_met: list[str] = snapshot.get("conditions_met", [])
    targets = snapshot.get("targets", [])
    tp_lines = "\n".join(
        f"🎯 TP{i + 1}\n{t['price']:.4f}" + (" (estrutural)" if t["source"] == "structural" else " (R múltiplo)")
        for i, t in enumerate(targets)
    )

    lines = [
        "🟢 ALPHAQUANT X",
        SEPARATOR,
        "",
        "🎯 OPORTUNIDADE DETECTADA",
        "",
        opportunity.asset,
        opportunity.timeframe,
        "",
        "📘 Playbook",
        opportunity.playbook,
        "",
        "📊 Score",
        f"{opportunity.score:.0f}/100",
        "",
        "🧠 Confiança",
        _confidence_label(opportunity.confidence),
        "",
        "📈 Direção",
        opportunity.direction.value,
        "",
        "💰 Entrada",
        f"{opportunity.entry:.4f}" if opportunity.entry is not None else "N/D",
        "",
        "🛑 Stop",
        f"{opportunity.stop:.4f}" if opportunity.stop is not None else "N/D",
        "",
        tp_lines,
        "",
        "⚖️ RR",
        f"1 : {opportunity.rr:.2f}" if opportunity.rr is not None else "N/D",
        "",
        SEPARATOR,
        "",
        "📌 EVIDÊNCIAS",
        *(f"✓ {c}" for c in conditions_met),
        "",
        SEPARATOR,
        "",
        "🧠 DECISÃO",
        "",
        "🟢 ENTRAR",
        "",
        SEPARATOR,
        "",
        "⚠️ Não é garantia de resultado.",
        "Gestão de risco é obrigatória.",
        "",
        "ALPHAQUANT X",
    ]
    return "\n".join(lines)


def format_future_message(opportunity: Opportunity) -> str:
    snapshot = opportunity.audit_snapshot or {}
    conditions_met: list[str] = snapshot.get("conditions_met", [])
    conditions_missing: list[str] = snapshot.get("conditions_missing", [])
    decision_info = snapshot.get("decision") or {}
    decision_reasons: list[str] = decision_info.get("reasons", [])

    # Future Opportunity "de verdade" (Fase 11, nunca passou pelo Decision
    # Engine): o próximo gatilho é o que ainda falta no próprio playbook.
    # Já um ESPERAR (playbook confirmado, só falta confiança) usa o motivo
    # do Decision Engine.
    next_trigger_lines = decision_reasons or conditions_missing or ["Aguardando confirmação adicional."]

    lines = [
        "🟡 ALPHAQUANT X",
        SEPARATOR,
        "",
        "🔭 FUTURE OPPORTUNITY",
        "",
        opportunity.asset,
        opportunity.timeframe,
        "",
        "📘 Playbook",
        opportunity.playbook,
        "",
        "📊 Score atual",
        f"{opportunity.score:.0f}/100",
        "",
        "🧩 Progresso",
        f"{opportunity.progress:.0f}%",
        "",
        "🧠 Confiança",
        _confidence_label(opportunity.confidence),
        "",
        SEPARATOR,
        "",
        "✅ CONDIÇÕES ATENDIDAS",
        *(f"✓ {c}" for c in conditions_met),
        "",
        "🎯 PRÓXIMO GATILHO",
        *next_trigger_lines,
        "",
        "Status:",
        "",
        "🟡 EM FORMAÇÃO",
        "",
        "Não é entrada.",
        "",
        "ALPHAQUANT X",
    ]
    return "\n".join(lines)


def format_system_online_message(active_strategies: int, symbols: int, scan_interval_minutes: int) -> str:
    """Seção 7 — primeira mensagem ao ligar o sistema."""
    lines = [
        "🟢 ALPHAQUANT X ONLINE",
        "",
        "Sistema iniciado com sucesso.",
        "",
        "🔎 Scanner:",
        "Ativo",
        "",
        "📊 Mercado:",
        "Bybit",
        "",
        "🪙 Ativos monitorados:",
        str(symbols),
        "",
        "⏱️ Scanner:",
        f"A cada {scan_interval_minutes} minutos",
        "",
        "🧠 Estratégias:",
        f"{active_strategies} ativas",
        "",
        "📡 Status:",
        "Procurando oportunidades...",
    ]
    return "\n".join(lines)


def format_scan_started_message(manual: bool, symbols_count: int, requested_by_username: str | None = None) -> str:
    """
    Enviada no INÍCIO de todo ciclo de scan (seção 6/68) — automático a
    cada SCAN_INTERVAL_MINUTES ou disparado na hora pelo comando
    `/analisar` do Telegram. Deixa claro pro grupo que o robô está de
    fato analisando, em vez de ficar em silêncio até achar (ou não) algo.
    """
    if manual:
        requester = f" (pedido por @{requested_by_username})" if requested_by_username else " (pedido manual)"
        header = f"🔍 ANÁLISE MANUAL INICIADA{requester}"
    else:
        header = "🔍 ANALISANDO O MERCADO"

    lines = [
        header,
        "",
        f"Escaneando {symbols_count} ativo(s)...",
        "",
        "ALPHAQUANT X",
    ]
    return "\n".join(lines)


def format_system_error_message(service: str, error: str) -> str:
    """Seção 42/48 — SYSTEM_ERROR. Enviado só na transição ONLINE ->
    DEGRADED (ver `worker/app/main.py`), nunca a cada ciclo com erro."""
    lines = [
        "🔴 ALPHAQUANT X — SYSTEM ERROR",
        "",
        "Serviço:",
        service,
        "",
        "Erro:",
        error,
        "",
        "O scanner continua tentando nos próximos ciclos.",
    ]
    return "\n".join(lines)


def format_system_recovered_message(service: str) -> str:
    lines = [
        "🟢 ALPHAQUANT X — RECUPERADO",
        "",
        "Serviço:",
        service,
        "",
        "Voltou a operar normalmente.",
    ]
    return "\n".join(lines)


_TP_EVENT_LABELS = {
    "TP1_HIT": "🎯 TP1", "TP2_HIT": "🎯 TP2", "TP3_HIT": "🎯 TP3",
    "TP4_HIT": "🎯 TP4", "TP5_HIT": "🎯 TP5",
}


def format_trade_update_message(trade, event) -> str:
    """
    Seção 45 (TP atingido) / 44 (invalidação) / 80 (fechamento) — uma
    mensagem por evento relevante de uma Trade já aberta (seção 96: isto
    é sobre a TRADE, não sobre o SIGNAL original, que já foi enviado por
    `format_signal_message`).
    """
    header = _TP_EVENT_LABELS.get(event.event_type)
    if header is not None:
        closed_statuses = {"CLOSED", "EXPIRED", "INVALIDATED", "STOP_HIT"}
        still_open = trade.status.value not in closed_statuses
        lines = [
            f"{header} — ALPHAQUANT X",
            "",
            f"{trade.asset} {trade.direction.value}",
            "",
            f"{header.split(' ', 1)[1]} atingido.",
            "",
            "Setup continua válido." if still_open else "Operação encerrada.",
            "",
            "Stop:",
            f"{float(trade.stop):.4f}",
        ]
        return "\n".join(lines)

    if event.event_type == "STOP":
        lines = [
            "🛑 ALPHAQUANT X — STOP",
            "",
            f"{trade.asset} {trade.direction.value}",
            "",
            f"Stop atingido em {event.price:.4f}.",
            "",
            f"Resultado: {trade.realized_r:+.2f}R",
        ]
        return "\n".join(lines)

    if event.event_type == "STOP_MOVED_TO_BREAKEVEN":
        lines = [
            "🔒 ALPHAQUANT X — BREAKEVEN",
            "",
            f"{trade.asset} {trade.direction.value}",
            "",
            "Stop movido para o preço de entrada após TP1.",
            "",
            f"Novo stop: {float(trade.stop):.4f}",
        ]
        return "\n".join(lines)

    # CLOSED / EXPIRED / genérico
    lines = [
        "⚪ ALPHAQUANT X — OPERAÇÃO ENCERRADA",
        "",
        f"{trade.asset} {trade.direction.value}",
        "",
        f"Resultado: {trade.result.value if trade.result else 'N/D'}",
        f"R: {trade.realized_r:+.2f}",
    ]
    return "\n".join(lines)


def format_invalidation_message(opportunity: Opportunity) -> str:
    snapshot = opportunity.audit_snapshot or {}
    reasons: list[str] = snapshot.get("quality_filter", {}).get("reasons", [])
    reason_lines = [f"❌ {r}" for r in reasons] if reasons else ["❌ Condições deixaram de ser atendidas"]

    lines = [
        "⚪ ALPHAQUANT X",
        "",
        "SETUP INVALIDADO",
        "",
        opportunity.asset,
        opportunity.timeframe,
        "",
        "Playbook:",
        opportunity.playbook,
        "",
        "Score anterior:",
        f"{opportunity.score:.0f}",
        "",
        "Motivo:",
        "",
        *reason_lines,
        "",
        "Status:",
        "",
        "REPROVADO",
        "",
        "Nenhuma entrada foi recomendada.",
    ]
    return "\n".join(lines)


def format_status_message(worker_row, settings) -> str:
    """/status (seção 43) — status real do sistema. Só reporta o que o
    sistema efetivamente monitora hoje (worker/scanner via heartbeat);
    não inventa linhas de serviços sem checagem real por trás."""
    if worker_row is None or worker_row.last_heartbeat is None:
        worker_line = "⚪ WORKER: nunca rodou um ciclo ainda"
    else:
        last_heartbeat = worker_row.last_heartbeat
        if last_heartbeat.tzinfo is None:
            # Alguns drivers (ex.: sqlite) não preservam timezone mesmo em
            # colunas DateTime(timezone=True) — nunca comparar naive com
            # aware sem normalizar antes.
            last_heartbeat = last_heartbeat.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - last_heartbeat
        age_min = int(age.total_seconds() // 60)
        icon = "🟢" if worker_row.status == "ONLINE" else "🔴"
        worker_line = f"{icon} WORKER: {worker_row.status} (último ciclo há {age_min}min)"
        if worker_row.error:
            worker_line += f"\n   ⚠️ {worker_row.error}"

    lines = [
        "📊 ALPHAQUANT X — STATUS",
        "",
        "🟢 API: ONLINE",
        worker_line,
        "",
        f"Scanner: a cada {settings.SCAN_INTERVAL_MINUTES}min",
        f"Ativos monitorados: {'AUTO (Bybit, ranqueado por liquidez)' if settings.SCAN_ASSETS.strip().upper() == 'AUTO' else len(settings.scan_assets)}",
        f"Timeframes: {', '.join(settings.scan_timeframes)}",
        f"Modo: {'🧪 TESTE' if settings.TEST_MODE else 'PRODUÇÃO'}",
    ]
    return "\n".join(lines)


def format_opportunities_list_message(opportunities: list[Opportunity]) -> str:
    """/oportunidades (seção 43) — melhores oportunidades atuais, dados
    reais do banco, nunca um exemplo fixo."""
    if not opportunities:
        return "📊 ALPHAQUANT X\n\nNenhuma oportunidade de alta qualidade no momento.\n\nIsso é um resultado válido — o sistema não força sinal."

    lines = ["🔥 MELHORES OPORTUNIDADES ATUAIS", ""]
    for i, opp in enumerate(opportunities, start=1):
        decision = opp.decision.value if opp.decision else "EM FORMAÇÃO"
        lines.append(f"{i}. {opp.asset} {opp.timeframe} — {opp.playbook}")
        lines.append(f"   {opp.direction.value} — Score {opp.score:.0f} — {decision}")
        if opp.rr:
            lines.append(f"   RR 1:{opp.rr:.1f}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_setups_forming_message(opportunities: list[Opportunity]) -> str:
    """/setups (seção 43) — setups em formação (FORMATION/ESPERAR)."""
    if not opportunities:
        return "👀 ALPHAQUANT X\n\nNenhum setup em formação no momento."

    lines = ["👀 SETUPS EM FORMAÇÃO", ""]
    for opp in opportunities:
        lines.append(f"• {opp.asset} {opp.timeframe} — {opp.playbook} ({opp.direction.value})")
        lines.append(f"  Score {opp.score:.0f} — progresso {opp.progress:.0f}%")
    return "\n".join(lines)


def format_open_trades_message(trades: list) -> str:
    """/abertas (seção 34/43) — operações abertas, com PnL real calculado
    contra o último preço já persistido em cada Trade (nunca busca preço
    novo aqui — o Monitoring Engine já atualiza isso a cada ciclo)."""
    if not trades:
        return "📊 ALPHAQUANT X\n\nNenhuma operação aberta no momento."

    lines = [f"📊 OPERAÇÕES ABERTAS ({len(trades)})", ""]
    for t in trades:
        pnl_line = f"   P&L: {t.realized_pnl_pct:+.2f}% ({t.realized_r:+.2f}R)" if t.last_price else "   P&L: aguardando primeira atualização de preço"
        lines.append(f"🟢 {t.asset} — {t.direction.value}")
        lines.append(f"   Entrada: {t.entry} — Atual: {t.last_price or 'N/D'}")
        lines.append(pnl_line)
        lines.append(f"   Estratégia: {t.strategy_name}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_closed_trades_message(trades: list) -> str:
    """/historico (seção 35/43) — últimas operações fechadas."""
    if not trades:
        return "📊 ALPHAQUANT X\n\nNenhuma operação fechada ainda."

    lines = [f"📊 HISTÓRICO — últimas {len(trades)} operações", ""]
    for t in trades:
        icon = "✅" if t.result and t.result.value == "WIN" else "❌" if t.result and t.result.value == "LOSS" else "🟡"
        lines.append(f"{icon} {t.asset} — {t.direction.value}")
        lines.append(f"   Resultado: {t.realized_r:+.2f}R — {t.status.value}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_help_message() -> str:
    lines = [
        "🤖 ALPHAQUANT X — COMANDOS",
        "",
        "/analisar — dispara uma análise manual imediata",
        "/relatorio — relatório completo das últimas 24h",
        "/status — status do sistema (API, worker, scanner)",
        "/oportunidades — melhores oportunidades atuais",
        "/setups — setups em formação",
        "/abertas — operações abertas",
        "/historico — últimas operações fechadas",
        "/help — esta mensagem",
    ]
    return "\n".join(lines)
