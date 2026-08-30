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


def format_market_scan_report(
    *,
    universe_size: int,
    stage1_count: int,
    stage2_count: int,
    top_gainers: list[tuple[str, float, float]],
    top_losers: list[tuple[str, float, float]],
    setups_watch: list[dict],
    setups_ready: list[dict],
) -> str:
    """Formata o relatório periódico / horário de inteligência de mercado do AlphaQuant X."""
    gainers_lines = ""
    for sym, chg, price in top_gainers[:5]:
        gainers_lines += f"  🟢 {sym}: +{chg:.2f}% (${price:.4f})\n"

    losers_lines = ""
    for sym, chg, price in top_losers[:5]:
        losers_lines += f"  🔴 {sym}: {chg:.2f}% (${price:.4f})\n"

    watch_lines = ""
    for s in setups_watch[:6]:
        d_emoji = "📈" if s.get("direction", "").lower() == "long" else "📉"
        score_val = s.get("score")
        score = f"⭐ {score_val:.0f}/100" if score_val else ""
        watch_lines += f"  {d_emoji} {s.get('asset')}: {s.get('strategy', 'Setup')} ({score})\n"

    ready_lines = ""
    for s in setups_ready[:5]:
        d_emoji = "🚀" if s.get("direction", "").lower() == "long" else "🔻"
        score_val = s.get("score")
        score = f"⭐ {score_val:.0f}/100" if score_val else ""
        ready_lines += f"  {d_emoji} {s.get('asset')}: {s.get('strategy', 'Setup')} ({score})\n"

    msg = (
        "🌐 ALPHAQUANT X — RADAR DE MERCADO\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Universo Bybit: {universe_size} pares\n"
        f"🔍 Filtro de Atividade (Stage 1): {stage1_count} pares\n"
        f"🔬 Análise Aprofundada (Stage 2): {stage2_count} pares\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "🚀 TOP 5 MAIORES ALTAS (24H):\n"
        f"{gainers_lines or '  (sem dados no momento)\n'}"
        "\n"
        "🔻 TOP 5 MAIORES QUEDAS (24H):\n"
        f"{losers_lines or '  (sem dados no momento)\n'}"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    if ready_lines:
        msg += (
            "🎯 CALLS / SETUPS CONFIRMADOS:\n"
            f"{ready_lines}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

    if watch_lines:
        msg += (
            "⏳ SETUPS EM FORMAÇÃO (AGUARDANDO CONFIRMAÇÃO):\n"
            f"{watch_lines}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
    else:
        msg += (
            "⏳ SETUPS EM FORMAÇÃO:\n"
            "  Nenhum setup em zona no momento. Varredura contínua 24/7.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

    msg += "📡 Scanner ativo | Monitorando mercado em tempo real."
    return msg

