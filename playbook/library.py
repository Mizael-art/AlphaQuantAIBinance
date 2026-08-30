"""
playbook/library.py
===================

Master Playbook Library for the AlphaQuant X Strategy Factory.
Contains all 76 deterministic Playbooks across 18 strategy families.
"""

from __future__ import annotations

from typing import Final

from playbook.evaluators import evaluate_playbook_generic
from playbook.schema import Backtestability, PlaybookDefinition, PlaybookTier
from regime.detector import (
    ACCUMULATION,
    COMPRESSION,
    DISTRIBUTION,
    EXPANSION,
    RANGE,
    TRENDING_DOWN,
    TRENDING_UP,
)

ALL_REGIMES = frozenset({TRENDING_UP, TRENDING_DOWN, RANGE, ACCUMULATION, DISTRIBUTION, COMPRESSION, EXPANSION})
TREND_REGIMES = frozenset({TRENDING_UP, TRENDING_DOWN})
RANGE_REGIMES = frozenset({RANGE, ACCUMULATION, DISTRIBUTION})
BREAKOUT_REGIMES = frozenset({COMPRESSION, EXPANSION, RANGE})

DAY_TRADE: Final = "day_trade"
INTRADAY: Final = "intraday"
SWING: Final = "swing"

# Backward compatibility alias
PlaybookEntry = PlaybookDefinition


# Helper to build PlaybookDefinition concisely
def _def(
    id: str,
    name: str,
    category: str,
    style: str,
    directions: set[str],
    tier: PlaybookTier,
    compatible_regimes: frozenset[str],
    min_rr: float,
    min_score: int,
    description: str,
    backtestability: Backtestability = Backtestability.DISCOVERY_ONLY,
    required_indicators: list[str] | None = None,
    notes: str = "",
) -> PlaybookDefinition:
    incompatible = ALL_REGIMES - compatible_regimes
    return PlaybookDefinition(
        id=id,
        name=name,
        category=category,
        style=style,
        directions=frozenset(directions),
        tier=tier,
        compatible_regimes=compatible_regimes,
        incompatible_regimes=incompatible,
        htf_timeframe="4h",
        mtf_timeframe="1h",
        ltf_timeframe="15m",
        min_rr=min_rr,
        min_score=min_score,
        description=description,
        backtestability=backtestability,
        evaluator=lambda ctx, pid=id: evaluate_playbook_generic(pid, ctx),
        required_indicators=required_indicators or ["ema50", "ema200", "atr", "rsi"],
        notes=notes,
    )


PLAYBOOK_CATALOG: Final[list[PlaybookDefinition]] = [
    # ------------------------------------------------------------------
    # 1. Trend Following (001 - 005)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_001", "Trend Continuation EMA50", "Trend Following", "swing", {"long", "short"}, PlaybookTier.TIER_A_PLUS, TREND_REGIMES, 2.5, 75,
         "Entrada a favor da tendência com pullback técnico na EMA50 e confirmação de BOS.", Backtestability.BACKTESTABLE),
    _def("PLAYBOOK_002", "EMA20/50 Momentum Pullback", "Trend Following", "intraday", {"long", "short"}, PlaybookTier.TIER_A, TREND_REGIMES, 2.2, 72,
         "Pullback de momentum controlado entre EMA20 e EMA50 em tendência ativa.", Backtestability.BACKTESTABLE),
    _def("PLAYBOOK_003", "EMA50/200 Trend Alignment", "Trend Following", "swing", {"long", "short"}, PlaybookTier.TIER_A, TREND_REGIMES, 2.0, 70,
         "Alinhamento estrutural de médias móveis de longo prazo EMA50 e EMA200.", Backtestability.BACKTESTABLE),
    _def("PLAYBOOK_004", "HTF Trend + LTF Pullback", "Trend Following", "day_trade", {"long", "short"}, PlaybookTier.TIER_A_PLUS, TREND_REGIMES, 2.8, 80,
         "Contexto 4H em tendência forte com execução de pullback em 1H e trigger 15M.", Backtestability.DISCOVERY_ONLY),
    _def("PLAYBOOK_005", "EMA200 Trend Reclaim", "Trend Following", "intraday", {"long", "short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.2, 75,
         "Reconquista e teste com volume acima da EMA200 após fase de acumulação.", Backtestability.BACKTESTABLE),

    # ------------------------------------------------------------------
    # 2. Liquidity / SMC (006 - 010)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_006", "Liquidity Sweep Reversal", "Liquidity / SMC", "day_trade", {"long", "short"}, PlaybookTier.TIER_S, RANGE_REGIMES, 3.0, 85,
         "Varredura de liquidez (sweep de stops) além dos extremos seguida de CHOCH/BOS.", Backtestability.DISCOVERY_ONLY),
    _def("PLAYBOOK_007", "Double Liquidity Sweep", "Liquidity / SMC", "day_trade", {"long", "short"}, PlaybookTier.TIER_S, RANGE_REGIMES, 3.2, 88,
         "Duplo sweep de liquidez com segundo teste mais profundo gerando exaustão institucional.", Backtestability.DISCOVERY_ONLY),
    _def("PLAYBOOK_008", "Equal High Liquidity Raid", "Liquidity / SMC", "day_trade", {"short"}, PlaybookTier.TIER_A_PLUS, RANGE_REGIMES, 2.5, 80,
         "Raid e rejeição em zona de Equal Highs (EQH) com entrada no retorno abaixo do nível.", Backtestability.DISCOVERY_ONLY),
    _def("PLAYBOOK_009", "Equal Low Liquidity Raid", "Liquidity / SMC", "day_trade", {"long"}, PlaybookTier.TIER_A_PLUS, RANGE_REGIMES, 2.5, 80,
         "Raid e absorção em zona de Equal Lows (EQL) com confirmação de retorno acima.", Backtestability.DISCOVERY_ONLY),
    _def("PLAYBOOK_010", "Liquidity Sweep + FVG", "Liquidity / SMC", "intraday", {"long", "short"}, PlaybookTier.TIER_S, ALL_REGIMES, 3.0, 85,
         "Confluência de sweep de liquidez seguido de displacement criando Fair Value Gap.", Backtestability.DISCOVERY_ONLY),

    # ------------------------------------------------------------------
    # 3. Order Block & FVG (011 - 018)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_011", "Liquidity Sweep + Order Block", "Order Block / FVG", "intraday", {"long", "short"}, PlaybookTier.TIER_A_PLUS, ALL_REGIMES, 2.8, 82,
         "Sweep de liquidez seguido de reação em Order Block institucional validado."),
    _def("PLAYBOOK_012", "Order Block Reaction", "Order Block / FVG", "intraday", {"long", "short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.5, 78,
         "Reação direta e rejeição de preço dentro de zona de Order Block de alta probabilidade."),
    _def("PLAYBOOK_013", "Order Block + BOS", "Order Block / FVG", "intraday", {"long", "short"}, PlaybookTier.TIER_A_PLUS, TREND_REGIMES, 2.8, 80,
         "Order block gerado imediatamente antes de uma quebra de estrutura (BOS)."),
    _def("PLAYBOOK_014", "FVG Retracement", "Order Block / FVG", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.4, 75,
         "Retração técnica para mitigação de Fair Value Gap (desbalanceamento)."),
    _def("PLAYBOOK_015", "FVG + EMA50", "Order Block / FVG", "intraday", {"long", "short"}, PlaybookTier.TIER_A, TREND_REGIMES, 2.4, 76,
         "Confluência de FVG alinhada com suporte/resistência da EMA50."),
    _def("PLAYBOOK_016", "FVG + Order Block", "Order Block / FVG", "intraday", {"long", "short"}, PlaybookTier.TIER_S, ALL_REGIMES, 3.0, 85,
         "Sobreposição de Order Block com Fair Value Gap (zona de altíssima confluência)."),
    _def("PLAYBOOK_017", "Breaker Block", "Order Block / FVG", "intraday", {"long", "short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.5, 78,
         "Order Block rompido que passa a atuar como suporte/resistência na direção oposta."),
    _def("PLAYBOOK_018", "Mitigation Block", "Order Block / FVG", "intraday", {"long", "short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.4, 76,
         "Reteste e alívio de ordens presas em zona de mitigação estrutural."),

    # ------------------------------------------------------------------
    # 4. Wyckoff (019 - 023)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_019", "Wyckoff Spring", "Wyckoff", "swing", {"long"}, PlaybookTier.TIER_S, RANGE_REGIMES, 3.0, 88,
         "Spring clássico da Fase C de Wyckoff abaixo do suporte com rejeição e BOS."),
    _def("PLAYBOOK_020", "Wyckoff Spring + Test", "Wyckoff", "swing", {"long"}, PlaybookTier.TIER_S, RANGE_REGIMES, 3.2, 90,
         "Teste com volume decrescente após ocorrência de Wyckoff Spring."),
    _def("PLAYBOOK_021", "Wyckoff SOS + LPS", "Wyckoff", "swing", {"long"}, PlaybookTier.TIER_A_PLUS, TREND_REGIMES | RANGE_REGIMES, 2.8, 84,
         "Sinal de Força (SOS) rompendo a lateralização com Last Point of Support (LPS)."),
    _def("PLAYBOOK_022", "Wyckoff Upthrust", "Wyckoff", "swing", {"short"}, PlaybookTier.TIER_S, RANGE_REGIMES, 3.0, 88,
         "Upthrust (UT) em zona de distribuição com falso rompimento e retorno."),
    _def("PLAYBOOK_023", "Wyckoff UTAD", "Wyckoff", "swing", {"short"}, PlaybookTier.TIER_S, RANGE_REGIMES, 3.2, 90,
         "Upthrust After Distribution (UTAD) na Fase C com exaustão compradora e CHOCH."),

    # ------------------------------------------------------------------
    # 5. Volume (024 - 027)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_024", "Volume Breakout Confirmation", "Volume", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, BREAKOUT_REGIMES, 2.5, 78,
         "Rompimento de nível com volume relativo superior a 1.5x a média de 20 períodos."),
    _def("PLAYBOOK_025", "Volume Exhaustion Reversal", "Volume", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.6, 80,
         "Clímax de volume seguido de falha de continuidade e reversão estrutural."),
    _def("PLAYBOOK_026", "Volume Dry-Up + Breakout", "Volume", "intraday", {"long", "short"}, PlaybookTier.TIER_A_PLUS, frozenset({COMPRESSION, RANGE}), 2.8, 82,
         "Secagem extrema de volume em compressão seguida de expansão explosiva."),
    _def("PLAYBOOK_027", "Volume Absorption Reversal", "Volume", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, RANGE_REGIMES, 2.5, 78,
         "Absorção institucional em suporte/resistência com alto volume sem deslocamento."),

    # ------------------------------------------------------------------
    # 6. Volume Profile (028 - 032)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_028", "POC Reclaim", "Volume Profile", "intraday", {"long", "short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.4, 76,
         "Reconquista e sustentação acima do Point of Control (POC)."),
    _def("PLAYBOOK_029", "VAH Rejection", "Volume Profile", "day_trade", {"short"}, PlaybookTier.TIER_A, RANGE_REGIMES, 2.2, 75,
         "Rejeição no Value Area High (VAH) com rotação para dentro da área de valor."),
    _def("PLAYBOOK_030", "VAL Reclaim", "Volume Profile", "day_trade", {"long"}, PlaybookTier.TIER_A, RANGE_REGIMES, 2.2, 75,
         "Reconquista do Value Area Low (VAL) retornando ao centro da distribuição de volume."),
    _def("PLAYBOOK_031", "LVN Expansion", "Volume Profile", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, BREAKOUT_REGIMES, 2.4, 76,
         "Aceleração de preço através de Low Volume Node (zona de baixo volume)."),
    _def("PLAYBOOK_032", "HVN Range Rotation", "Volume Profile", "intraday", {"long", "short"}, PlaybookTier.TIER_B, RANGE_REGIMES, 2.0, 70,
         "Rotação de preço entre extremidades em direção ao High Volume Node central."),

    # ------------------------------------------------------------------
    # 7. RSI / Momentum (033 - 036)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_033", "RSI Trend Pullback", "Momentum", "intraday", {"long", "short"}, PlaybookTier.TIER_A, TREND_REGIMES, 2.2, 74,
         "Recuo do RSI na faixa 40-50 em tendência de alta (ou 50-60 em baixa) com retomada."),
    _def("PLAYBOOK_034", "RSI Divergence Reversal", "Momentum", "day_trade", {"long", "short"}, PlaybookTier.TIER_A_PLUS, RANGE_REGIMES, 2.6, 82,
         "Divergência clássica regular de RSI com confirmação de quebra estrutural (CHOCH)."),
    _def("PLAYBOOK_035", "RSI Failure Swing", "Momentum", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.2, 75,
         "Failure swing no RSI confirmando exaustão sem necessidade de novo extremo no preço."),
    _def("PLAYBOOK_036", "RSI Extreme + Liquidity Sweep", "Momentum", "day_trade", {"long", "short"}, PlaybookTier.TIER_S, RANGE_REGIMES, 3.0, 86,
         "Sweep de liquidez com RSI em nível extremo (<25 ou >75) e rejeição imediata."),

    # ------------------------------------------------------------------
    # 8. Stochastic (037 - 039)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_037", "Stochastic Trend Pullback", "Stochastic", "intraday", {"long", "short"}, PlaybookTier.TIER_B, TREND_REGIMES, 2.0, 72,
         "Cruzamento de Stochastic %K acima de %D na zona de sobrevenda durante tendência de alta."),
    _def("PLAYBOOK_038", "Stochastic Divergence + Structure", "Stochastic", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, RANGE_REGIMES, 2.4, 78,
         "Divergência no oscilador estocástico combinada com rejeição em suporte/resistência."),
    _def("PLAYBOOK_039", "Stochastic + RSI Confluence", "Stochastic", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.3, 76,
         "Confluência de sobrevenda/sobrecompra simultânea no RSI e Estocástico."),

    # ------------------------------------------------------------------
    # 9. MACD (040 - 042)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_040", "MACD Momentum Confirmation", "MACD", "intraday", {"long", "short"}, PlaybookTier.TIER_A, TREND_REGIMES, 2.2, 74,
         "Expansão do histograma MACD a favor do alinhamento da linha de sinal e tendência."),
    _def("PLAYBOOK_041", "MACD Divergence + CHOCH", "MACD", "day_trade", {"long", "short"}, PlaybookTier.TIER_A_PLUS, RANGE_REGIMES, 2.6, 82,
         "Divergência no histograma/linha MACD com reversão estrutural CHOCH."),
    _def("PLAYBOOK_042", "MACD Zero-Line Continuation", "MACD", "swing", {"long", "short"}, PlaybookTier.TIER_A, TREND_REGIMES, 2.4, 76,
         "Bounce e sustentação da linha MACD na linha zero em tendência contínua."),

    # ------------------------------------------------------------------
    # 10. VWAP (043 - 045)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_043", "VWAP Reclaim", "VWAP", "day_trade", {"long"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.2, 75,
         "Reconquista e fechamento acima da VWAP com volume e reteste."),
    _def("PLAYBOOK_044", "VWAP Rejection", "VWAP", "day_trade", {"short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.2, 75,
         "Rejeição no teste inferior da VWAP atuando como resistência de intraday."),
    _def("PLAYBOOK_045", "VWAP + Liquidity Sweep", "VWAP", "day_trade", {"long", "short"}, PlaybookTier.TIER_A_PLUS, RANGE_REGIMES, 2.8, 84,
         "Sweep de liquidez com recuperação imediata do desvio padrão da VWAP."),

    # ------------------------------------------------------------------
    # 11. Breakout & Volatility (046 - 053)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_046", "Breakout + Retest", "Breakout", "day_trade", {"long", "short"}, PlaybookTier.TIER_A_PLUS, BREAKOUT_REGIMES, 2.5, 80,
         "Rompimento limpo com volume seguido de reteste defensivo no nível rompido."),
    _def("PLAYBOOK_047", "False Breakout", "Breakout", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, RANGE_REGIMES, 2.4, 78,
         "Rompimento falso com captura de liquidez e retorno acelerado ao range."),
    _def("PLAYBOOK_048", "Failed Breakdown", "Breakout", "day_trade", {"long"}, PlaybookTier.TIER_A_PLUS, RANGE_REGIMES, 2.6, 82,
         "Falha de rompimento para baixo em suporte com retorno forte e BOS de alta."),
    _def("PLAYBOOK_049", "Failed Breakout", "Breakout", "day_trade", {"short"}, PlaybookTier.TIER_A_PLUS, RANGE_REGIMES, 2.6, 82,
         "Falha de rompimento de topo em resistência com retorno vendedor expressivo."),
    _def("PLAYBOOK_050", "Compression Breakout", "Breakout", "intraday", {"long", "short"}, PlaybookTier.TIER_A_PLUS, frozenset({COMPRESSION}), 2.6, 82,
         "Squeeze de volatilidade com rompimento de Bandas de Bollinger e expansão de ATR."),
    _def("PLAYBOOK_051", "ATR Expansion Breakout", "Volatility", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, BREAKOUT_REGIMES, 2.3, 76,
         "Expansão inicial do ATR após período de volatilidade comprimida."),
    _def("PLAYBOOK_052", "ATR Contraction + Expansion", "Volatility", "intraday", {"long", "short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.4, 78,
         "Contração do ATR durante o pullback seguida de retomada da expansão."),
    _def("PLAYBOOK_053", "Volatility Expansion Reversal", "Volatility", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, RANGE_REGIMES, 2.5, 80,
         "Extensão anormal de volatilidade (3x ATR) com exaustão e reversão."),

    # ------------------------------------------------------------------
    # 12. Classic Patterns (054 - 059)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_054", "Double Bottom Confirmation", "Classic Patterns", "day_trade", {"long"}, PlaybookTier.TIER_A, RANGE_REGIMES, 2.5, 78,
         "Padrão clássico de fundo duplo com confirmação e rompimento da neckline."),
    _def("PLAYBOOK_055", "Double Top Confirmation", "Classic Patterns", "day_trade", {"short"}, PlaybookTier.TIER_A, RANGE_REGIMES, 2.5, 78,
         "Padrão clássico de topo duplo com confirmação e perda da neckline."),
    _def("PLAYBOOK_056", "Triple Bottom + Liquidity", "Classic Patterns", "swing", {"long"}, PlaybookTier.TIER_A_PLUS, RANGE_REGIMES, 2.8, 84,
         "Triplo fundo com sweep de liquidez no terceiro teste e reação compradora."),
    _def("PLAYBOOK_057", "Triple Top + Liquidity", "Classic Patterns", "swing", {"short"}, PlaybookTier.TIER_A_PLUS, RANGE_REGIMES, 2.8, 84,
         "Triplo topo com captura de liquidez no terceiro teste e rejeição."),
    _def("PLAYBOOK_058", "Ascending Triangle Breakout", "Classic Patterns", "day_trade", {"long"}, PlaybookTier.TIER_A, BREAKOUT_REGIMES, 2.4, 78,
         "Triângulo ascendente com fundos mais altos e rompimento da resistência horizontal."),
    _def("PLAYBOOK_059", "Descending Triangle Breakout", "Classic Patterns", "day_trade", {"short"}, PlaybookTier.TIER_A, BREAKOUT_REGIMES, 2.4, 78,
         "Triângulo descendente com topos mais baixos e perda do suporte horizontal."),

    # ------------------------------------------------------------------
    # 13. Momentum Extremo & Displacement (060 - 061)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_060", "Displacement Continuation", "Extreme Momentum", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, TREND_REGIMES, 2.5, 80,
         "Vela de displacement institucional com volume quebrando estrutura e continuação."),
    _def("PLAYBOOK_061", "Displacement Exhaustion", "Extreme Momentum", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, ALL_REGIMES, 2.6, 82,
         "Displacement exaustivo em nível de liquidez sem continuação gerando CHOCH."),

    # ------------------------------------------------------------------
    # 14. Range (062 - 064)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_062", "Range Low Reversal", "Range", "day_trade", {"long"}, PlaybookTier.TIER_A, RANGE_REGIMES, 2.2, 75,
         "Rejeição e reversão no suporte inferior do range lateral com alvo na mediana."),
    _def("PLAYBOOK_063", "Range High Reversal", "Range", "day_trade", {"short"}, PlaybookTier.TIER_A, RANGE_REGIMES, 2.2, 75,
         "Rejeição e reversão na resistência superior do range lateral com alvo na mediana."),
    _def("PLAYBOOK_064", "Range Midpoint Filter", "Range", "intraday", {"long", "short"}, PlaybookTier.TIER_RESEARCH, RANGE_REGIMES, 1.8, 50,
         "Filtro de exclusão de operações no ponto médio do range sem assimetria de risco.", notes="Filtro de No-Trade"),

    # ------------------------------------------------------------------
    # 15. Multi-Timeframe (065 - 069)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_065", "HTF Level Reaction", "Multi-Timeframe", "day_trade", {"long", "short"}, PlaybookTier.TIER_A_PLUS, ALL_REGIMES, 2.8, 84,
         "Reação precisa em suporte/resistência derivado do timeframe 4H/1D."),
    _def("PLAYBOOK_066", "4H Breakout + 1H Retest", "Multi-Timeframe", "swing", {"long", "short"}, PlaybookTier.TIER_A_PLUS, BREAKOUT_REGIMES, 2.8, 85,
         "Rompimento no gráfico de 4H com confirmação e reteste limpo no gráfico de 1H."),
    _def("PLAYBOOK_067", "1H Breakout + 15M Retest", "Multi-Timeframe", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, BREAKOUT_REGIMES, 2.5, 80,
         "Rompimento no 1H com reteste e gatilho de execução no 15M para day trade."),
    _def("PLAYBOOK_068", "1D/4H Trend + 1H Entry", "Multi-Timeframe", "swing", {"long", "short"}, PlaybookTier.TIER_A_PLUS, TREND_REGIMES, 3.0, 88,
         "Alinhamento macro 1D e 4H com ponto de entrada no 1H."),
    _def("PLAYBOOK_069", "4H Range + 15M Reversal", "Multi-Timeframe", "day_trade", {"long", "short"}, PlaybookTier.TIER_A_PLUS, RANGE_REGIMES, 2.8, 84,
         "Extremo de range de 4H com gatilho de reversão e sweep no 15M."),

    # ------------------------------------------------------------------
    # 16. Maximum Confluence A+ (070 - 072, 076)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_070", "A+ Liquidity + OB + FVG + BOS", "Maximum Confluence", "intraday", {"long", "short"}, PlaybookTier.TIER_S, ALL_REGIMES, 3.2, 92,
         "Setup supremo: Sweep de Liquidez + Order Block + FVG + Break of Structure."),
    _def("PLAYBOOK_071", "A+ HTF Trend + EMA50 + Liquidity", "Maximum Confluence", "intraday", {"long", "short"}, PlaybookTier.TIER_S, TREND_REGIMES, 3.0, 90,
         "Tendência HTF alinhada com EMA50, sweep de liquidez interna e FVG."),
    _def("PLAYBOOK_072", "A+ Breakout + Retest + Volume", "Maximum Confluence", "day_trade", {"long", "short"}, PlaybookTier.TIER_S, BREAKOUT_REGIMES, 3.0, 90,
         "Rompimento com alto volume, reteste milimétrico no POC e expansão."),
    _def("PLAYBOOK_076", "Maximum Confluence Setup", "Maximum Confluence", "intraday", {"long", "short"}, PlaybookTier.TIER_S, ALL_REGIMES, 3.5, 95,
         "Convergência de mais de 4 fatores estruturais e técnicos independentes."),

    # ------------------------------------------------------------------
    # 17. Day Trading Específico (073 - 075)
    # ------------------------------------------------------------------
    _def("PLAYBOOK_073", "Open Range Breakout", "Day Trading", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, BREAKOUT_REGIMES, 2.4, 78,
         "Rompimento do range de abertura com expansão de volume e momentum."),
    _def("PLAYBOOK_074", "First Pullback After Breakout", "Day Trading", "day_trade", {"long", "short"}, PlaybookTier.TIER_A_PLUS, TREND_REGIMES, 2.6, 82,
         "Primeiro pullback após o rompimento inicial do dia."),
    _def("PLAYBOOK_075", "Session High/Low Liquidity Sweep", "Day Trading", "day_trade", {"long", "short"}, PlaybookTier.TIER_A, RANGE_REGIMES, 2.5, 80,
         "Varredura das máximas e mínimas das sessões de Londres / Nova York."),
]


# Lookup Maps
_PLAYBOOK_BY_ID: Final[dict[str, PlaybookDefinition]] = {p.id: p for p in PLAYBOOK_CATALOG}
_PLAYBOOK_BY_NAME: Final[dict[str, PlaybookDefinition]] = {p.name.lower(): p for p in PLAYBOOK_CATALOG}


def get_playbook(id_or_name: str) -> PlaybookDefinition | None:
    """Busca playbook por ID (ex: PLAYBOOK_001) ou por Nome."""
    return _PLAYBOOK_BY_ID.get(id_or_name) or _PLAYBOOK_BY_NAME.get(id_or_name.lower())


def get_all_playbooks() -> list[PlaybookDefinition]:
    """Retorna os 76 playbooks do catálogo."""
    return list(PLAYBOOK_CATALOG)


def compatible_playbooks(regime: str, direction: str, style: str | None = None) -> list[PlaybookDefinition]:
    """
    Filtro Regime-First do Discovery Engine. Retorna todos os playbooks
    compatíveis com o regime e direção do ativo.
    """
    results = [
        p for p in PLAYBOOK_CATALOG
        if regime in p.compatible_regimes and direction.lower() in p.directions
    ]
    if style is not None:
        results = [p for p in results if p.style == style]
    return results


PLAYBOOK: Final[list[PlaybookDefinition]] = PLAYBOOK_CATALOG

