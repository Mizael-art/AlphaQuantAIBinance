"""
Formatação das mensagens Telegram (seções 16-18 do master prompt).

Cada template usa exclusivamente dados reais já calculados e persistidos
(Score, RR, targets, conditions_met/missing, decision) — nunca um valor
de exemplo ou inventado. Os templates da especificação original são
ilustrativos ("os valores acima são apenas formato de exemplo"); aqui
cada campo é preenchido com o que o sistema efetivamente sabe.
"""
from __future__ import annotations

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
