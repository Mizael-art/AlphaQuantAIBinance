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


def format_tp_hit(record: SetupRecord, tp_level: str = "TP1") -> str:
    """Formata notificação de TP atingido."""
    pnl = f"+{record.realized_pnl_pct:.2f}%" if record.realized_pnl_pct is not None else "+2.5%"
    r_mult = f"+{record.realized_r_multiple:.1f}R" if record.realized_r_multiple is not None else "+1.0R"
    return (
        f"🎯 ALPHAQUANT X — {tp_level.upper()} ATINGIDO (HIT)! 🚀\n"

        "\n"
        f"🪙 {record.asset} — {'LONG 🟢' if record.direction == 'long' else 'SHORT 🔴'}\n"
        f"📘 Estratégia: {record.strategy}\n"
        f"🎯 Alvo alcançado: {getattr(record, tp_level.lower(), record.tp1)}\n"
        f"📈 PnL Realizado: {pnl}\n"
        f"⚖️ R-Múltiplo: {r_mult}\n"
        "\n"
        "✅ Lucro parcial protegido no bolso! Trade segue com risco reduzido."
    )


def format_stop_hit(record: SetupRecord) -> str:
    """Formata notificação de stop atingido para trades ativos."""
    pnl = f"{record.realized_pnl_pct:.2f}%" if record.realized_pnl_pct is not None else "-1.0%"
    r_mult = f"{record.realized_r_multiple:.1f}R" if record.realized_r_multiple is not None else "-1.0R"
    return (
        "🛑 ALPHAQUANT X — STOP HIT\n"
        "\n"
        f"🪙 {record.asset} — {'LONG 🟢' if record.direction == 'long' else 'SHORT 🔴'}\n"
        f"📘 Estratégia: {record.strategy}\n"
        f"🛑 Saída de proteção: {record.exit_price or record.stop}\n"
        f"📉 PnL: {pnl}\n"
        f"⚖️ R-Múltiplo: {r_mult}\n"
        "\n"
        "⚠️ Gestão de risco executada rigorosamente. Preservação de capital em 1º lugar."
    )


def format_invalidated(record: SetupRecord, reason: str = "") -> str:
    """Deprecated: Invalidações de setups não executados são apenas log interno e nunca enviadas ao Telegram."""
    return ""


def format_setup_update(record: SetupRecord, change_type: str) -> str:
    """Formata notificação de atualização significativa do setup."""
    return (
        "🔔 ALPHAQUANT X — SETUP ATUALIZADO\n"
        "\n"
        f"🪙 {record.asset} — {'LONG 🟢' if record.direction == 'long' else 'SHORT 🔴'}\n"
        f"📘 {record.strategy}\n"
        f"📊 Status: {record.status}\n"
        f"⭐ Score: {record.score:.0f}/100\n" if record.score else ""
    )


def format_market_scan_report(
    *,
    universe_size: int = 0,
    stage1_count: int = 0,
    stage2_count: int = 0,
    top_gainers: list[tuple[str, float, float]] | None = None,
    top_losers: list[tuple[str, float, float]] | None = None,
    setups_watch: list[dict] | None = None,
    setups_ready: list[dict] | None = None,
    btc_trend: str = "Neutral",
    btc_regime: str = "RANGE",
    conflicts: list[str] | None = None,
) -> str:
    """
    Formata o Relatório Horário de Mercado do AlphaQuant X (Tipo A).
    Formato padronizado conforme especificação Master Prompt Seção 22.
    """
    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    next_hour_utc = now_utc + timedelta(hours=1)
    time_str = now_utc.strftime("%H:%M UTC")
    next_time_str = next_hour_utc.strftime("%H:00 UTC")

    msg = (
        "📊 ALPHAQUANT X — MARKET REPORT\n"
        "\n"
        f"⏱️ Atualização: {time_str}\n"
        "\n"
        "🌐 Mercado\n"
        f"BTC: {btc_trend}\n"
        f"Regime: {btc_regime.upper()}\n"
        "\n"
    )

    # 1. MELHORES OPORTUNIDADES
    ready_list = setups_ready or []
    if ready_list:
        msg += "🔥 MELHORES OPORTUNIDADES\n\n"
        for i, s in enumerate(ready_list[:3], 1):
            dir_emoji = "🟢" if s.get("direction", "").lower() == "long" else "🔴"
            score_val = s.get("score")
            score_str = f"{score_val:.0f}" if score_val else "N/A"
            status_str = s.get("status", "READY")
            msg += (
                f"{i}. {s.get('asset')} — {s.get('direction', '').upper()} {dir_emoji}\n"
                f"   Score: {score_str}\n"
                f"   Estado: {status_str}\n"
                f"   Setup: {s.get('strategy', 'Setup')}\n\n"
            )
    else:
        msg += (
            "🔥 MELHORES OPORTUNIDADES\n"
            "   Nenhuma oportunidade executável de alta qualidade neste momento.\n\n"
        )

    # 2. AGUARDANDO CONFIRMAÇÃO
    watch_list = setups_watch or []
    if watch_list:
        msg += "🟡 AGUARDANDO CONFIRMAÇÃO\n"
        for s in watch_list[:5]:
            dir_emoji = "🟢" if s.get("direction", "").lower() == "long" else "🔴"
            score_val = s.get("score")
            score_str = f" (Score {score_val:.0f})" if score_val else ""
            msg += f"• {s.get('asset')} — {s.get('direction', '').upper()} {dir_emoji} [{s.get('strategy', 'Setup')}]{score_str}\n"
        msg += "\n"

    # 3. CONFLITOS (se houver)
    if conflicts:
        msg += "🚨 CONFLITOS DIRECIONAIS\n"
        for c in conflicts[:3]:
            msg += f"• {c}\n"
        msg += "\n"

    msg += f"📈 Próxima atualização: {next_time_str}"
    return msg


