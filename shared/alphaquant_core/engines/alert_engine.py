"""
Alert Engine (seções 19-20 do master prompt).

Decide SE uma Opportunity deve gerar um alerta — nunca manda mensagem a
cada atualização marginal de score (seção 19: "Não gerar spam"). Usa a
própria tabela `alerts` como histórico: consulta o último alerta já
enviado para essa Opportunity para decidir se o evento atual é
genuinamente novo.

Regras:
- REPROVAR sem nunca ter sido alertada antes -> nada (seção 69: "nenhuma
  oportunidade de qualidade" é um resultado válido, não precisa virar
  mensagem de invalidação de algo que nunca foi anunciado).
- ENTRAR pela primeira vez (ou após não ter sido SIGNAL antes) -> SIGNAL.
- ESPERAR pela primeira vez (nunca alertada) -> FUTURE.
- REPROVAR depois de já ter sido SIGNAL ou FUTURE -> INVALIDATION (o
  setup que estava sendo acompanhado deixou de existir).
- Qualquer repetição do mesmo tipo dentro do cooldown (30 min, seção 20)
  -> nada, mesmo que o texto interno mude ligeiramente.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from alphaquant_core.db.models import Alert, AlertType, DecisionResult, Opportunity

COOLDOWN = timedelta(minutes=30)


def _last_alert(db: Session, opportunity_id: int) -> Alert | None:
    return (
        db.query(Alert)
        .filter_by(opportunity_id=opportunity_id)
        .order_by(Alert.created_at.desc())
        .first()
    )


def decide_alert(db: Session, opportunity: Opportunity) -> AlertType | None:
    last = _last_alert(db, opportunity.id)

    if last is not None and datetime.now(timezone.utc) - last.created_at < COOLDOWN:
        return None  # dentro do cooldown — nunca repete, mesmo que o tipo mudasse

    if opportunity.decision is None:
        # Future Opportunity (Fase 11): playbook ainda não confirmou, só
        # progride — nunca passou pelo Quality Filter/Decision Engine.
        if last is None:
            return AlertType.FUTURE
        return None

    if opportunity.decision == DecisionResult.ENTRAR:
        if last is None or last.alert_type != AlertType.SIGNAL:
            return AlertType.SIGNAL
        return None

    if opportunity.decision == DecisionResult.ESPERAR:
        if last is None:
            return AlertType.FUTURE
        return None

    if opportunity.decision == DecisionResult.REPROVAR:
        if last is not None and last.alert_type in (AlertType.SIGNAL, AlertType.FUTURE):
            return AlertType.INVALIDATION
        return None

    return None
