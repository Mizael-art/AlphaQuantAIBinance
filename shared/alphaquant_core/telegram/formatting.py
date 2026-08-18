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
