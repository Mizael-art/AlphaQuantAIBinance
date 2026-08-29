"""
notifications/formatter.py
=============================

Formatação padronizada de mensagens para o Telegram.

Todos os dados vêm do motor real — nunca inventados.
Linguagem baseada em setup confirmado / cenário / invalidação.
Nunca afirma "vai subir" como certeza.
"""

from __future__ import annotations

from persistence.models import SetupRecord


def format_new_call(record: SetupRecord, decision_info: dict | None = None) -> str:
    """Formata uma nova call de entrada confirmada."""
    direction_emoji = "📈" if record.direction == "long" else "📉"
    direction_label = "LONG" if record.direction == "long" else "SHORT"

    entry_str = ""
    if record.entry_zone_low and record.entry_zone_high:
        entry_str = f"{record.entry_zone_low:.4f} – {record.entry_zone_high:.4f}"
    elif record.entry_zone_low:
        entry_str = f"{record.entry_zone_low:.4f}"

    rr_str = f"1 : {record.rr:.1f}" if record.rr else "N/A"
    score_str = f"{record.score:.0f}/100" if record.score else "N/A"
    strategy_str = record.strategy or "N/A"

    # Construir confirmações baseadas no reason_for_change real
    confirmations = ""
    if decision_info:
        reasons = decision_info.get("reasons", [])
        for r in reasons[:7]:  # Max 7 confirmações
            confirmations += f"✓ {r}\n"

    msg = (
        "🟢 ALPHAQUANT X\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "🎯 NOVA OPORTUNIDADE\n"
        "\n"
        f"🪙 {record.asset}\n"
        f"{direction_emoji} {direction_label}\n"
        "\n"
        f"📘 Playbook\n"
        f"{strategy_str}\n"
        "\n"
        f"⭐ Score\n"
        f"{score_str}\n"
        "\n"
        f"📍 Entrada\n"
        f"{entry_str}\n"
        "\n"
        f"🛑 Stop\n"
        f"{record.stop if record.stop else 'N/A'}\n"
        "\n"
        f"🎯 TP1\n"
        f"{record.tp1 if record.tp1 else 'N/A'}\n"
        "\n"
        f"🎯 TP2\n"
        f"{record.tp2 if record.tp2 else 'N/A'}\n"
        "\n"
        f"🎯 TP3\n"
        f"{record.tp3 if record.tp3 else 'N/A'}\n"
        "\n"
        f"⚖️ RR\n"
        f"{rr_str}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )

    if confirmations:
        msg += (
            "\n"
            "📌 CONFIRMAÇÕES\n"
            "\n"
            f"{confirmations}"
            "\n"
            "━━━━━━━━━━━━━━━━━━\n"
        )

    msg += (
        "\n"
        "⚠️ Não é garantia de resultado.\n"
        "Gerencie o risco corretamente.\n"
    )

    return msg


def format_tp_hit(record: SetupRecord, tp_level: str) -> str:
    """Formata notificação de TP atingido."""
    tp_emoji = {"TP1": "🎯", "TP2": "🎯🎯", "TP3": "🎯🎯🎯"}.get(tp_level, "🎯")
    return (
        f"{tp_emoji} ALPHAQUANT X\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "\n"
        f"✅ {tp_level} ATINGIDO\n"
        "\n"
        f"🪙 {record.asset}\n"
        f"{'📈 LONG' if record.direction == 'long' else '📉 SHORT'}\n"
        f"📘 {record.strategy}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )


def format_stop_hit(record: SetupRecord) -> str:
    """Formata notificação de stop atingido."""
    return (
        "🔴 ALPHAQUANT X\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "❌ STOP ATINGIDO\n"
        "\n"
        f"🪙 {record.asset}\n"
        f"{'📈 LONG' if record.direction == 'long' else '📉 SHORT'}\n"
        f"📘 {record.strategy}\n"
        f"🛑 Stop: {record.stop}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )


def format_invalidated(record: SetupRecord, reason: str = "") -> str:
    """Formata notificação de setup invalidado."""
    return (
        "⚠️ ALPHAQUANT X\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "🚫 SETUP INVALIDADO\n"
        "\n"
        f"🪙 {record.asset}\n"
        f"{'📈 LONG' if record.direction == 'long' else '📉 SHORT'}\n"
        f"📘 {record.strategy}\n"
        + (f"\n📝 Motivo: {reason}\n" if reason else "")
        + "\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )


def format_setup_update(record: SetupRecord, change_type: str) -> str:
    """Formata notificação de atualização significativa do setup."""
    return (
        "🔔 ALPHAQUANT X\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "\n"
        f"📋 SETUP ATUALIZADO → {change_type.upper()}\n"
        "\n"
        f"🪙 {record.asset}\n"
        f"{'📈 LONG' if record.direction == 'long' else '📉 SHORT'}\n"
        f"📘 {record.strategy}\n"
        f"📊 Status: {record.status}\n"
        f"⭐ Score: {record.score:.0f}/100\n" if record.score else ""
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )
