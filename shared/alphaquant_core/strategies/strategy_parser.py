"""
strategy_parser — transforma o PROMPT de uma estrategia em uma arvore de
Condition executavel.

Por que um mini-DSL de linhas em vez de NLP livre sobre paragrafo
(secao 13/14 pediam "interpretar o prompt"): interpretar prosa livre em
portugues de forma confiavel exigiria um LLM na hora da execucao (custo,
latencia e nao-determinismo a cada um dos 50+ ativos x 15 minutos) e
tornaria o Quality Filter (secao 20) incapaz de garantir "nao inventar
condicao" (secao 15). A alternativa mais robusta e compativel com o
scanner determinista existente e' um vocabulario de linhas estruturadas
-- e' isso que strategy_validator valida contra o vocabulario suportado
e o que strategy_runner executa bar-a-bar sem lookahead.

Formato aceito (linhas, case-insensitive, comentarios com #):

    NAME: Liquidity Sweep Reversal
    TIMEFRAMES: 4H, 1H, 15M
    MODE: SWING
    DIRECTION: LONG            # LONG | SHORT | AUTO (infere da 1a condicao de regime/BOS/CHOCH)

    CONDITIONS:
      BOS(4H) == BULLISH
      CHOCH(15M) == BULLISH
      RSI14(1H) < 40
      VOLUME > VOLUME_AVG20
      OR LIQUIDITY_SWEEP(1H) == BELOW
      NOT VOLATILITY_CONTRACTION < 0.7

    STOP: SWING_LOW            # SWING_LOW | SWING_HIGH | ATR(mult) | FIXED_PCT(pct)
    TARGETS: RR 1.5, RR 3.0
    INVALIDATION: CHOCH(15M) == BEARISH

Cada linha dentro de CONDITIONS vira uma Condition. O conector padrao
entre linhas e' AND; prefixar a linha com "OR " ou "NOT " muda o
conector daquela linha especifica (secao 14: AND/OR/NOT).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class ParseError(Exception):
    """Prompt malformado — nunca deve virar uma estrategia executavel silenciosa."""


class Connector(str, Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


_COND_RE = re.compile(
    r"^(?P<field>[A-Z][A-Z0-9_]*)"
    r"(\((?P<timeframe>[^)]*)\))?"
    r"\s*(?P<op>==|!=|>=|<=|>|<)\s*"
    r"(?P<value>.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Condition:
    raw: str
    field: str
    op: str
    value: str
    timeframe: str | None = None
    connector: Connector = Connector.AND


@dataclass(frozen=True)
class StopRule:
    kind: str                 # SWING_LOW | SWING_HIGH | ATR | FIXED_PCT | UNSUPPORTED
    param: float | None = None


@dataclass(frozen=True)
class TargetRule:
    kind: str                 # RR | PRICE
    value: float
    exit_pct: float | None = None  # secao 34 — multi-TP com % de saida


@dataclass(frozen=True)
class StrategyPrompt:
    """Resultado bruto do parser — ainda nao validado contra o vocabulario suportado."""
    name: str
    raw_prompt: str
    timeframes: list[str]
    mode: str
    direction: str  # LONG | SHORT | AUTO
    conditions: list[Condition]
    stop: StopRule
    targets: list[TargetRule]
    invalidation: list[Condition] = field(default_factory=list)


def _split_kv_line(line: str) -> tuple[str, str] | None:
    if ":" not in line:
        return None
    key, _, value = line.partition(":")
    return key.strip().upper(), value.strip()


def _parse_condition_line(line: str) -> Condition:
    connector = Connector.AND
    stripped = line.strip()
    upper = stripped.upper()
    if upper.startswith("OR "):
        connector = Connector.OR
        stripped = stripped[3:].strip()
    elif upper.startswith("NOT "):
        connector = Connector.NOT
        stripped = stripped[4:].strip()
    elif upper.startswith("AND "):
        stripped = stripped[4:].strip()

    m = _COND_RE.match(stripped)
    if not m:
        # tenta normalizar espacos em torno de operadores antes de desistir
        normalized = re.sub(r"\s+", " ", stripped)
        m = _COND_RE.match(normalized)
    if not m:
        raise ParseError(f"condicao nao reconhecida (formato esperado CAMPO[(TF)] OP VALOR): {line!r}")

    return Condition(
        raw=line.strip(),
        field=m.group("field").upper(),
        op=m.group("op"),
        value=m.group("value").strip(),
        timeframe=m.group("timeframe").strip().upper() if m.group("timeframe") else None,
        connector=connector,
    )


def _parse_stop(value: str) -> StopRule:
    v = value.strip().upper()
    if v == "SWING_LOW":
        return StopRule(kind="SWING_LOW")
    if v == "SWING_HIGH":
        return StopRule(kind="SWING_HIGH")
    m = re.match(r"^ATR\((?P<mult>[\d.]+)\)$", v)
    if m:
        return StopRule(kind="ATR", param=float(m.group("mult")))
    m = re.match(r"^FIXED_PCT\((?P<pct>[\d.]+)\)$", v)
    if m:
        return StopRule(kind="FIXED_PCT", param=float(m.group("pct")))
    # Regra 15 / 35: nunca inventar um stop. Se o prompt pedir algo que o
    # engine nao sabe calcular, marca como UNSUPPORTED em vez de assumir
    # um tipo de stop por conta propria.
    return StopRule(kind="UNSUPPORTED", param=None)


def _parse_targets(value: str) -> list[TargetRule]:
    targets: list[TargetRule] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        pct = None
        pct_match = re.search(r"(\d+(\.\d+)?)\s*%\s*$", chunk)
        if pct_match:
            pct = float(pct_match.group(1))
            chunk = chunk[: pct_match.start()].strip()
        m = re.match(r"^RR\s+([\d.]+)$", chunk, re.IGNORECASE)
        if m:
            targets.append(TargetRule(kind="RR", value=float(m.group(1)), exit_pct=pct))
            continue
        m = re.match(r"^PRICE\s+([\d.]+)$", chunk, re.IGNORECASE)
        if m:
            targets.append(TargetRule(kind="PRICE", value=float(m.group(1)), exit_pct=pct))
            continue
        raise ParseError(f"alvo nao reconhecido (use 'RR <numero>' ou 'PRICE <numero>'): {chunk!r}")
    return targets


def parse_prompt(name: str, prompt: str) -> StrategyPrompt:
    """
    Faz o parsing estrutural do prompt. NAO valida se os campos usados
    existem no MarketContext — isso e' responsabilidade do
    strategy_validator (separacao pedida pela secao 15: parsing e'
    sintaxe, validation e' semantica/dado disponivel).
    """
    lines = [ln.rstrip() for ln in prompt.splitlines()]
    timeframes: list[str] = []
    mode = "SCANNER"
    direction = "AUTO"
    conditions: list[Condition] = []
    invalidation: list[Condition] = []
    stop = StopRule(kind="UNSUPPORTED")
    targets: list[TargetRule] = []

    section: str | None = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        upper = line.upper()
        if upper in ("CONDITIONS:", "CONDITIONS"):
            section = "CONDITIONS"
            continue
        if upper in ("INVALIDATION:", "INVALIDATION") :
            section = "INVALIDATION"
            continue

        kv = _split_kv_line(line)
        if kv is not None and kv[0] in (
            "NAME", "TIMEFRAMES", "MODE", "DIRECTION", "STOP", "TARGETS", "INVALIDATION",
        ):
            key, val = kv
            if key == "NAME":
                name = val or name
            elif key == "TIMEFRAMES":
                timeframes = [tf.strip().upper() for tf in val.split(",") if tf.strip()]
            elif key == "MODE":
                mode = val.strip().upper()
            elif key == "DIRECTION":
                direction = val.strip().upper()
            elif key == "STOP":
                stop = _parse_stop(val)
            elif key == "TARGETS":
                targets = _parse_targets(val)
            elif key == "INVALIDATION" and val:
                invalidation.append(_parse_condition_line(val))
            section = None
            continue

        if section == "CONDITIONS":
            conditions.append(_parse_condition_line(line))
        elif section == "INVALIDATION":
            invalidation.append(_parse_condition_line(line))
        # linhas fora de qualquer secao/chave conhecida sao ignoradas (permite
        # texto livre de documentacao/racional dentro do prompt, secao 13)

    if not conditions:
        raise ParseError("prompt sem bloco CONDITIONS: nenhuma condicao para avaliar")
    if direction not in ("LONG", "SHORT", "AUTO"):
        raise ParseError(f"DIRECTION invalido: {direction!r} (use LONG, SHORT ou AUTO)")

    return StrategyPrompt(
        name=name,
        raw_prompt=prompt,
        timeframes=timeframes or ["1H"],
        mode=mode,
        direction=direction,
        conditions=conditions,
        stop=stop,
        targets=targets,
        invalidation=invalidation,
    )
