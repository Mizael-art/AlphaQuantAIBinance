"""
strategy_service — persistência do Strategy Lab (seções 23-29), usando o
parser/validator/runner puros da Fase 1 (`alphaquant_core.strategies`).

Mesma regra de versionamento do `StrategyRegistry` em memória (Fase 1),
agora em banco: `update_strategy` sempre cria uma `StrategyVersion` nova
e move `Strategy.current_version_id` — nunca sobrescreve um prompt em
vigor. `archive_strategy` é soft-delete; histórico nunca é apagado.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from alphaquant_core.db.models import Strategy, StrategyStatus, StrategyVersion
from alphaquant_core.strategies.strategy_parser import ParseError, parse_prompt
from alphaquant_core.strategies.strategy_validator import validate_prompt


def _build_version(db: Session, strategy_id: int, name: str, prompt_raw: str, version_label: str,
                    author: str | None = None, change_note: str | None = None) -> StrategyVersion:
    try:
        parsed = parse_prompt(name, prompt_raw)
        validation = validate_prompt(parsed)
        status = validation.status  # VALID | UNSUPPORTED_CONDITION | INVALID
        errors = validation.errors
        unsupported = validation.unsupported_conditions
    except ParseError as exc:
        status = "INVALID"
        errors = [str(exc)]
        unsupported = []

    version = StrategyVersion(
        strategy_id=strategy_id, version_label=version_label, prompt_raw=prompt_raw,
        status=status, errors=errors, unsupported_conditions=unsupported,
        author=author, change_note=change_note,
    )
    db.add(version)
    db.flush()
    return version


def create_strategy(
    db: Session, name: str, prompt_raw: str, *, mode: str = "SCANNER",
    active: bool = True, author: str | None = None,
) -> Strategy:
    strategy = Strategy(name=name, mode=mode, status=StrategyStatus.ACTIVE if active else StrategyStatus.INACTIVE)
    db.add(strategy)
    db.flush()

    version = _build_version(db, strategy.id, name, prompt_raw, version_label="v1", author=author)
    strategy.current_version_id = version.id
    db.commit()
    db.refresh(strategy)
    return strategy


def update_strategy(
    db: Session, strategy: Strategy, *, prompt_raw: str | None = None, mode: str | None = None,
    author: str | None = None, change_note: str | None = None,
) -> Strategy:
    """Cria uma NOVA versão — nunca sobrescreve a atual (seção 28)."""
    if prompt_raw is not None:
        next_label = f"v{len(strategy.versions) + 1}"
        version = _build_version(
            db, strategy.id, strategy.name, prompt_raw, version_label=next_label,
            author=author, change_note=change_note,
        )
        strategy.current_version_id = version.id
    if mode is not None:
        strategy.mode = mode
    db.commit()
    db.refresh(strategy)
    return strategy


def set_status(db: Session, strategy: Strategy, status: StrategyStatus) -> Strategy:
    strategy.status = status
    db.commit()
    db.refresh(strategy)
    return strategy


def archive_strategy(db: Session, strategy: Strategy) -> Strategy:
    """DELETAR == ARCHIVE (seção 29) — histórico de versões nunca é apagado."""
    return set_status(db, strategy, StrategyStatus.ARCHIVED)


def duplicate_strategy(db: Session, strategy: Strategy, new_name: str | None = None) -> Strategy:
    name = new_name or f"{strategy.name} (cópia)"
    return create_strategy(db, name=name, prompt_raw=strategy.current_version.prompt_raw, mode=strategy.mode, active=False)


def get_strategy(db: Session, strategy_id: int) -> Strategy | None:
    return db.get(Strategy, strategy_id)


def list_strategies(db: Session, status: StrategyStatus | None = None) -> list[Strategy]:
    q = db.query(Strategy)
    if status is not None:
        q = q.filter(Strategy.status == status)
    return q.order_by(Strategy.created_at).all()


def is_runnable(strategy: Strategy) -> bool:
    return strategy.status == StrategyStatus.ACTIVE and strategy.current_version.status == "VALID"


def to_dict(strategy: Strategy) -> dict:
    v = strategy.current_version
    return {
        "id": strategy.id,
        "name": strategy.name,
        "mode": strategy.mode,
        "status": strategy.status.value,
        "current_version": {
            "id": v.id,
            "version_label": v.version_label,
            "prompt_raw": v.prompt_raw,
            "status": v.status,
            "errors": v.errors,
            "unsupported_conditions": v.unsupported_conditions,
            "created_at": v.created_at.isoformat(),
            "author": v.author,
            "change_note": v.change_note,
        } if v else None,
        "version_count": len(strategy.versions),
        "is_runnable": is_runnable(strategy),
        "created_at": strategy.created_at.isoformat(),
        "updated_at": strategy.updated_at.isoformat(),
    }
