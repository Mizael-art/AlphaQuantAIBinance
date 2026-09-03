"""
scoring/engine.py
====================

Multi-Score Engine (Documento 2, seção 12; Documento Master, seção 25).

Nota de honestidade metodológica: o Documento Master (seção 25) propõe
pesos para um OVERALL SCORE a partir de 10 fatores (Contexto, Regime,
Estrutura, Liquidez, Volume/Order Flow, SMC/Wyckoff, Playbook,
Timing/Entry, RR/Risk, Statistical Edge) que não mapeiam 1:1 com os 9
scores nomeados do Documento 2 seção 12 (Quality/Tradeability/Timing/
Risk/Asymmetry/Confirmation/Setup Maturity/Statistical Edge/Overall).
Este módulo adapta os dois: calcula os 9 scores nomeados a partir dos
inputs disponíveis hoje (technical score já existente, estrutura,
distância até a zona, RR, contexto BTC, volatilidade, correlação,
estatística do Playbook quando existir) e deriva o OVERALL como uma
média ponderada EXPLÍCITA dos 8 (pesos declarados abaixo, ajustáveis --
Documento Master seção 25 já autoriza isso: "você pode modificar os
pesos se os dados/backtests demonstrarem que outra distribuição é
superior"). Nenhum score aqui é probabilidade de lucro (Documento
Master, seção 75) -- é só a pontuação dos critérios atuais.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Pesos do OVERALL_SCORE -- somam 1.0. Ver nota de honestidade acima:
# esta é uma adaptação explícita da tabela do Documento Master seção 25,
# não uma cópia literal (os 9 scores nomeados do Documento 2 seção 12
# não são os mesmos 10 fatores da seção 25 do Documento Master).
_OVERALL_WEIGHTS: dict[str, float] = {
    "quality": 0.20,
    "confirmation": 0.15,
    "tradeability": 0.10,
    "timing": 0.10,
    "risk": 0.15,
    "asymmetry": 0.15,
    "setup_maturity": 0.10,
    "statistical_edge": 0.05,
}


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


@dataclass(frozen=True, slots=True)
class OpportunityScore:
    quality: float
    tradeability: float
    timing: float
    risk: float
    asymmetry: float
    confirmation: float
    setup_maturity: float
    statistical_edge: float
    overall: float
    statistical_edge_available: bool
    setup_score: float = 0.0
    entry_score: float = 0.0
    trade_score: float = 0.0
    factors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "quality_score": round(self.quality, 1),
            "tradeability_score": round(self.tradeability, 1),
            "timing_score": round(self.timing, 1),
            "risk_score": round(self.risk, 1),
            "asymmetry_score": round(self.asymmetry, 1),
            "confirmation_score": round(self.confirmation, 1),
            "setup_maturity_score": round(self.setup_maturity, 1),
            "statistical_edge_score": round(self.statistical_edge, 1),
            "statistical_edge_available": self.statistical_edge_available,
            "setup_score": round(self.setup_score, 1),
            "entry_score": round(self.entry_score, 1),
            "trade_score": round(self.trade_score, 1),
            "overall_opportunity_score": round(self.overall, 1),
            "factors": self.factors,
        }


def _asymmetry_from_rr(rr: float | None) -> float:
    if rr is None or rr <= 0:
        return 0.0
    if rr < 1.0:
        return 0.0  # RR abaixo de 1:1 é completamente inaceitável
    if rr < 1.5:
        return 20.0
    if rr < 2.0:
        return 40.0
    if rr < 2.5:
        return 65.0
    if rr < 3.0:
        return 80.0
    if rr < 4.0:
        return 90.0
    return 100.0


def _distance_curve(distance_to_zone_pct: float | None, near_value: float, far_value: float) -> float:
    """Curva genérica usada por TIMING e SETUP_MATURITY -- quanto mais perto da zona, maior o score."""
    if distance_to_zone_pct is None:
        return far_value
    if distance_to_zone_pct <= 0.3:
        return near_value
    if distance_to_zone_pct <= 0.8:
        return near_value * 0.90
    if distance_to_zone_pct <= 1.5:
        return near_value * 0.75
    if distance_to_zone_pct <= 2.5:
        return near_value * 0.45
    return far_value


def compute_opportunity_score(
    *,
    trend: str,
    bos: bool,
    choch: bool,
    regime_compatible: bool,
    rr: float | None,
    distance_to_zone_pct: float | None,
    volatility_bucket: str,
    btc_context: str | None,
    correlation_penalty: bool,
    playbook_stats: dict | None = None,
    volume_expansion: bool = False,
    rsi_alignment: bool = False,
    obstacle_ahead: bool = False,
) -> OpportunityScore:
    """
    Calcula os scores detalhados e deriva a arquitetura de 3 Scores:
    - Setup Score (60%): Contexto, regime, estrutura HTF, alinhamento BTC e compatibilidade de playbook.
    - Entry Score (40%): Localização/distância, confirmação (BOS/Volume/RSI), e ausência de obstáculos imediatos.
    - Trade Score: (0.60 * Setup Score) + (0.40 * Entry Score).
    """
    factors: list[str] = []

    # --- 1. SETUP SCORE (HTF Context, Regime, Structure, BTC) ---
    s_score = 40.0
    if regime_compatible:
        s_score += 25.0
        factors.append("Regime e Playbook compatíveis.")
    else:
        s_score -= 20.0
        factors.append("Incompatível com o regime de mercado atual.")

    if trend in ("Bullish", "Bearish"):
        s_score += 15.0
        factors.append(f"Tendência HTF definida ({trend}).")
    
    if bos:
        s_score += 10.0
        factors.append("Estrutura HTF confirmada com BOS.")
    if choch:
        s_score -= 15.0
        factors.append("Alerta de reversão estrutural (CHOCH).")

    if btc_context == "BTC_SUPPORTIVE":
        s_score += 10.0
        factors.append("Contexto BTC favorável.")
    elif btc_context == "BTC_HOSTILE":
        s_score -= 20.0
        factors.append("Contexto BTC hostil à direção do trade.")

    setup_score = _clamp(s_score)

    # --- 2. ENTRY SCORE (Location, Trigger, Volume, Obstacles, Asymmetry) ---
    e_score = 30.0
    # Proximidade da zona
    if distance_to_zone_pct is not None:
        if distance_to_zone_pct <= 0.5:
            e_score += 30.0
            factors.append("Preço na zona ideal de entrada.")
        elif distance_to_zone_pct <= 1.2:
            e_score += 20.0
        elif distance_to_zone_pct <= 2.2:
            e_score += 10.0
        else:
            e_score -= 15.0
            factors.append("Entrada esticada (distante da zona de valor).")
    else:
        e_score -= 10.0

    if volume_expansion:
        e_score += 15.0
        factors.append("Expansão de volume confirma fluxo institucional.")
    if rsi_alignment:
        e_score += 10.0
    if obstacle_ahead:
        e_score -= 25.0
        factors.append("Obstáculo/resistência imediata bloqueia o alvo (baixo room to run).")

    # Bônus ou penalidade por RR real
    if rr is not None:
        if rr >= 2.5:
            e_score += 15.0
        elif rr < 1.5:
            e_score -= 20.0
            factors.append("RR insuficiente.")

    entry_score = _clamp(e_score)

    # --- 3. TRADE SCORE COMBINADO ---
    trade_score = _clamp((0.60 * setup_score) + (0.40 * entry_score))

    # --- Métricas legadas para compatibilidade de API ---
    quality = setup_score
    confirmation = _clamp(50.0 + (30.0 if bos else 0.0) - (30.0 if choch else 0.0) + (20.0 if regime_compatible else -20.0))
    tradeability = _clamp(_distance_curve(distance_to_zone_pct, 90.0, 20.0))
    timing = _clamp(_distance_curve(distance_to_zone_pct, 90.0, 15.0) + (10.0 if volume_expansion else 0.0))
    setup_maturity = _clamp(_distance_curve(distance_to_zone_pct, 95.0, 10.0))
    
    risk = 100.0
    if volatility_bucket == "EXTREME":
        risk -= 25.0
        factors.append("Volatilidade extrema.")
    elif volatility_bucket == "HIGH":
        risk -= 10.0
    if correlation_penalty:
        risk -= 25.0
        factors.append("Exposição altamente correlacionada.")
    if choch or obstacle_ahead:
        risk -= 15.0
    risk = _clamp(risk)

    asymmetry = _clamp(_asymmetry_from_rr(rr))

    stats_available = bool(playbook_stats and playbook_stats.get("sample_size", 0) >= 30)
    statistical_edge = _clamp(50.0 + (playbook_stats.get("win_rate", 50.0) - 50.0) * 0.6) if stats_available else 50.0

    return OpportunityScore(
        quality=quality,
        tradeability=tradeability,
        timing=timing,
        risk=risk,
        asymmetry=asymmetry,
        confirmation=confirmation,
        setup_maturity=setup_maturity,
        statistical_edge=statistical_edge,
        overall=trade_score,
        statistical_edge_available=stats_available,
        setup_score=setup_score,
        entry_score=entry_score,
        trade_score=trade_score,
        factors=factors,
    )

