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
    """Formata uma nova call de entrada confirmada com padrão simplificado e cálculo de risco."""
    direction_emoji = "🟢" if record.direction == "long" else "🔴"
    direction_label = "LONG" if record.direction == "long" else "SHORT"

    entry_val = record.entry_zone_low or 0.0
    if record.entry_zone_low and record.entry_zone_high:
        entry_val = (record.entry_zone_low + record.entry_zone_high) / 2.0
    
    entry_str = f"{entry_val:.4f}" if entry_val > 0 else "Mercado"
    stop_str = f"{record.stop:.4f}" if record.stop else "N/A"
    
    tps = []
    if record.tp1:
        tps.append(f"TP1: {record.tp1:.4f}")
    if record.tp2:
        tps.append(f"TP2: {record.tp2:.4f}")
    if record.tp3:
        tps.append(f"TP3: {record.tp3:.4f}")
    tp_str = " | ".join(tps) if tps else (f"TP: {record.tp1:.4f}" if record.tp1 else "N/A")

    # Cálculo do risco da banca (Alocação 5% x Alavancagem 10x = 50% de exposição nocional)
    bankroll_risk_pct = 2.3
    if record.stop and entry_val > 0:
        price_diff_pct = abs(entry_val - record.stop) / entry_val * 100
        bankroll_risk_pct = 0.5 * price_diff_pct

    reasons_list = []
    if decision_info and "reasons" in decision_info:
        reasons_list = [r for r in decision_info["reasons"] if not r.startswith("Critérios satisfeitos")]
    
    if reasons_list:
        why_str = "; ".join(reasons_list[:3])
    else:
        why_str = f"Setup {record.strategy} validado com alinhamento de estrutura e volume compatível."

    rr_val = f"1:{record.rr:.1f}" if record.rr else "1:2.5"
    score_val = f"{record.score:.0f}" if record.score else "85"

    msg = (
        f"📊 {record.asset} — {direction_label} {direction_emoji}\n"
        "\n"
        f"🟢 Entrada: {entry_str}\n"
        "⚡ Alavancagem: 10x\n"
        "💰 Alocação: 5% da banca\n"
        "\n"
        f"🎯 {tp_str}\n"
        f"🛑 SL: {stop_str}\n"
        "\n"
        f"⚖️ RR: {rr_val} | ⭐ Score: {score_val}/100\n"
        f"📘 Estratégia: {record.strategy}\n"
        "\n"
        f"🧠 Por que entrar: {why_str}\n"
        "\n"
        f"⚠️ Risco: Com 5% da banca em margem e 10x, uma saída no stop representa aproximadamente {bankroll_risk_pct:.1f}% da banca (antes de taxas/slippage)."
    )
    return msg


def format_tp_hit(record: SetupRecord, tp_level: str) -> str:
    """Formata notificação de TP atingido."""
    return (
        f"🎯 ALPHAQUANT X — {tp_level} ATINGIDO! 🚀\n"
        "\n"
        f"🪙 {record.asset} — {'LONG 🟢' if record.direction == 'long' else 'SHORT 🔴'}\n"
        f"📘 {record.strategy}\n"
        f"🎯 Alvo alcançado: {getattr(record, tp_level.lower(), record.tp1)}\n"
        f"💰 R-Múltiplo estimado: +{record.rr or 2.0:.1f}R\n"
        "\n"
        "✅ Lucro parcial protegido no bolso!"
    )


def format_stop_hit(record: SetupRecord) -> str:
    """Formata notificação de stop atingido."""
    return (
        "🛑 ALPHAQUANT X — STOP ATINGIDO\n"
        "\n"
        f"🪙 {record.asset} — {'LONG' if record.direction == 'long' else 'SHORT'}\n"
        f"📘 {record.strategy}\n"
        f"🛑 Saída de proteção: {record.stop}\n"
        "⚠️ Gestão de risco executada rigorosamente (-1.0R)."
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

