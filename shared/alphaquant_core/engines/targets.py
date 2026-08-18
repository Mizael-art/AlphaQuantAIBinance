"""
Projeção de TP1/TP2/TP3 e RR (seção 68: ENTRY -> STOP -> TARGETS -> RR).

Prioriza alvos estruturais reais (o próximo swing HIGH acima da entrada,
para LONG; o próximo swing LOW abaixo, para SHORT) — nunca inventa um
nível de preço. Um swing a menos de 1R de distância da entrada é tratado
como ruído, não como alvo útil (ver MIN_RR_FOR_STRUCTURAL_TARGET), e é
descartado. Quando não há swings estruturais suficientes à frente,
completa com múltiplos de R (2R/3R/4R), que é prática padrão de gestão de
risco, não um "alvo fabricado" — e cada alvo é marcado com sua origem
(`structural` ou `r_multiple`) para o Evidence Panel nunca confundir os
dois.
"""
from __future__ import annotations

from dataclasses import dataclass

from alphaquant_core.engines.structure import Swing, SwingType
from alphaquant_core.playbooks.base import Direction


@dataclass(frozen=True)
class Target:
    price: float
    source: str  # "structural" | "r_multiple"


@dataclass(frozen=True)
class TargetResult:
    entry: float
    stop: float
    risk: float
    targets: list[Target]
    rr: float  # calculado sobre o TP1 (primeiro alvo), conforme seção 30

    @property
    def tp1(self) -> float | None:
        return self.targets[0].price if len(self.targets) > 0 else None

    @property
    def tp2(self) -> float | None:
        return self.targets[1].price if len(self.targets) > 1 else None

    @property
    def tp3(self) -> float | None:
        return self.targets[2].price if len(self.targets) > 2 else None


R_MULTIPLES_FALLBACK = (2.0, 3.0, 4.0)
MIN_RR_FOR_STRUCTURAL_TARGET = 1.0  # um swing a menos de 1R de distância é ruído, não um alvo útil


def compute_targets(
    swings: list[Swing],
    direction: Direction,
    entry: float,
    stop: float,
) -> TargetResult | None:
    """
    Devolve None se o stop não representar uma invalidação real (mesmo
    lado da entrada, ou risco zero) — o Quality Filter (Fase 6) trata
    isso como bloqueio absoluto, mas o Targets Engine já recusa calcular
    algo sem sentido matemático.
    """
    if direction is Direction.LONG:
        risk = entry - stop
    else:
        risk = stop - entry

    if risk <= 0:
        return None

    min_distance = risk * MIN_RR_FOR_STRUCTURAL_TARGET
    structural: list[float] = []
    if direction is Direction.LONG:
        structural = sorted({
            s.price for s in swings if s.type is SwingType.HIGH and s.price - entry >= min_distance
        })
    else:
        structural = sorted(
            {s.price for s in swings if s.type is SwingType.LOW and entry - s.price >= min_distance},
            reverse=True,
        )

    targets: list[Target] = [Target(price=p, source="structural") for p in structural[:3]]

    # completa até 3 alvos com múltiplos de R, sem duplicar um nível já usado
    for multiple in R_MULTIPLES_FALLBACK:
        if len(targets) >= 3:
            break
        price = entry + multiple * risk if direction is Direction.LONG else entry - multiple * risk
        if any(abs(t.price - price) < 1e-9 for t in targets):
            continue
        targets.append(Target(price=price, source="r_multiple"))

    targets = targets[:3]
    if not targets:
        return None

    tp1 = targets[0].price
    rr = abs(tp1 - entry) / risk

    return TargetResult(entry=entry, stop=stop, risk=risk, targets=targets, rr=rr)
