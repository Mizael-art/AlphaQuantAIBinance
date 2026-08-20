"""
strategy_runner — PromptStrategy: uma estrategia nascida de um PROMPT que
implementa a MESMA interface `Playbook` dos 10 playbooks hardcoded
(alphaquant_core.playbooks.base.Playbook). Por isso o Playbook Engine
existente (playbooks/engine.py::evaluate_all) roda estrategias novas sem
precisar de nenhuma mudanca no core do scanner — exatamente o requisito
da secao 12/17/75 ("sem precisar alterar o core do sistema").
"""
from __future__ import annotations

from alphaquant_core.playbooks.base import Direction, Playbook, PlaybookContext, PlaybookResult
from alphaquant_core.strategies.strategy_context import (
    KNOWN_BUT_UNSUPPORTED_FIELDS,
    SUPPORTED_FIELDS,
    get_field,
)
from alphaquant_core.strategies.strategy_parser import Condition, Connector, StrategyPrompt

_NUMERIC_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
}


def _resolve_value_side(ctx: PlaybookContext, token: str) -> float | str | None:
    """O lado direito de uma condicao pode ser: um numero literal, outro
    campo do contexto (ex.: `VOLUME > VOLUME_AVG20`), ou um ROTULO
    literal (ex.: `REGIME == BULLISH`, `LIQUIDITY_SWEEP == BELOW`) — so'
    tratamos como campo se o token bater com o vocabulario de campos
    conhecido; caso contrario e' um rotulo textual comparado como-esta."""
    stripped = token.strip()
    try:
        return float(stripped)
    except ValueError:
        pass
    upper = stripped.upper()
    if upper in SUPPORTED_FIELDS or upper in KNOWN_BUT_UNSUPPORTED_FIELDS:
        return get_field(ctx, upper)
    return upper


def _eval_single(ctx: PlaybookContext, cond: Condition) -> bool | None:
    """True/False, ou None se o dado necessario nao esta disponivel
    (nunca vira False silenciosamente — vira 'nao avaliavel' e conta
    como condicao faltante, nao como condicao rejeitada)."""
    left = get_field(ctx, cond.field)
    if left is None:
        return None
    right = _resolve_value_side(ctx, cond.value)
    if right is None:
        return None

    if cond.op in _NUMERIC_OPS:
        try:
            return _NUMERIC_OPS[cond.op](float(left), float(right))
        except (TypeError, ValueError):
            return None

    # == / != — comparacao textual (rotulos: BULLISH, BEARISH, ABOVE, BELOW...)
    left_s = str(left).strip().upper()
    right_s = str(right).strip().upper()
    if cond.op == "==":
        return left_s == right_s
    if cond.op == "!=":
        return left_s != right_s
    return None


def _combine(results: list[tuple[Condition, bool | None]]) -> tuple[bool, list[str], list[str]]:
    """
    Combina os resultados condicao-a-condicao respeitando AND/OR/NOT por
    linha (secao 14). Semantica adotada (documentada por ser a parte
    "nao especificada" que a secao 74 pede para decidir sozinho):
      - AND (padrao) e NOT: obrigatorias.
      - OR: satisfaz o grupo se QUALQUER uma das linhas OR for verdadeira,
        E as obrigatorias tambem precisam ser verdadeiras.
    """
    met: list[str] = []
    missing: list[str] = []

    mandatory_ok = True
    or_group: list[Condition] = []
    or_group_ok = False
    has_or_group = False

    for cond, value in results:
        label = cond.raw
        if cond.connector == Connector.OR:
            has_or_group = True
            or_group.append(cond)
            if value is True:
                or_group_ok = True
                met.append(label)
            elif value is False:
                missing.append(label)
            else:
                missing.append(f"{label} (dado indisponivel)")
            continue

        if cond.connector == Connector.NOT:
            ok = value is False  # NOT so passa se a condicao for explicitamente falsa
        else:  # AND
            ok = value is True

        if ok:
            met.append(label if cond.connector != Connector.NOT else f"NOT {label}")
        else:
            mandatory_ok = False
            missing.append(label if value is not None else f"{label} (dado indisponivel)")

    matched = mandatory_ok and (or_group_ok if has_or_group else True)
    return matched, met, missing


class PromptStrategy(Playbook):
    """Adaptador: StrategyPrompt (ja validado) -> Playbook executavel."""

    def __init__(self, prompt: StrategyPrompt, version: str = "v1"):
        self.name = prompt.name
        self.version = version
        self._prompt = prompt

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        results = [(c, _eval_single(ctx, c)) for c in self._prompt.conditions]
        matched, met, missing = _combine(results)
        total = max(len(results), 1)
        progress = round(100.0 * len(met) / total, 1)

        direction = self._infer_direction(ctx)
        entry = ctx.last_close if matched else None
        stop = self._compute_stop(ctx) if matched else None

        notes = ""
        if matched and stop is None:
            # secao 8/15/35: sem stop tecnico valido, NUNCA vira entrada confirmada
            matched = False
            notes = "STOP_INSUFFICIENT_DATA"

        return PlaybookResult(
            playbook=self.name,
            matched=matched,
            direction=direction,
            progress=progress,
            conditions_met=met,
            conditions_missing=missing,
            entry=entry,
            stop=stop,
            notes=notes,
        )

    def _infer_direction(self, ctx: PlaybookContext) -> Direction | None:
        if self._prompt.direction in ("LONG", "SHORT"):
            return Direction(self._prompt.direction)
        # AUTO: usa o regime mais recente do proprio contexto
        if ctx.regime == "BULLISH":
            return Direction.LONG
        if ctx.regime == "BEARISH":
            return Direction.SHORT
        return None

    def _compute_stop(self, ctx: PlaybookContext) -> float | None:
        rule = self._prompt.stop
        direction = self._infer_direction(ctx)
        if rule.kind == "SWING_LOW":
            lows = [s.price for s in ctx.swings if s.label and s.label.value in ("HL", "LL")]
            return lows[-1] if lows else None
        if rule.kind == "SWING_HIGH":
            highs = [s.price for s in ctx.swings if s.label and s.label.value in ("HH", "LH")]
            return highs[-1] if highs else None
        if rule.kind == "ATR":
            atr = ctx.indicators.get("atr14")
            if atr is None or rule.param is None:
                return None
            offset = atr * rule.param
            return ctx.last_close - offset if direction == Direction.LONG else ctx.last_close + offset
        if rule.kind == "FIXED_PCT":
            if rule.param is None:
                return None
            offset = ctx.last_close * (rule.param / 100.0)
            return ctx.last_close - offset if direction == Direction.LONG else ctx.last_close + offset
        return None

    def compute_targets(self, ctx: PlaybookContext, entry: float, stop: float) -> list[dict]:
        """RR -> preco (secao 21/34). Nao faz parte do PlaybookResult (que
        so tem 1 campo `stop`) porque multi-TP com % de saida e' um
        conceito novo desta camada — o Trade Tracker (Fase 3) consome
        isso diretamente do PromptStrategy."""
        direction = self._infer_direction(ctx)
        risk = abs(entry - stop)
        out = []
        for t in self._prompt.targets:
            if t.kind == "RR":
                price = entry + risk * t.value if direction == Direction.LONG else entry - risk * t.value
            else:  # PRICE
                price = t.value
            out.append({"price": price, "rr": t.value if t.kind == "RR" else None, "exit_pct": t.exit_pct})
        return out
