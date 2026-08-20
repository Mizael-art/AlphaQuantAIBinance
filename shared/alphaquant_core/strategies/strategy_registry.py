"""
strategy_registry — CRUD + versionamento de estrategias (secoes 25-29).

Implementacao em memoria (thread-safe com lock simples) que serve dois
papeis:
  1. Hoje: permite o Strategy Engine e os testes rodarem sem depender da
     API/Postgres ainda estarem no ar.
  2. Depois (Fase 5 — Strategy Lab UI): `to_dict`/`from_dict` em cada
     dataclass sao o contrato de serializacao que os modelos SQLAlchemy
     de api/app/models (strategies, strategy_versions) devem espelhar,
     e `StrategyRegistry` pode trocar seu dict interno por queries no
     Postgres sem mudar a interface publica (create/update/list/get/...).

Regra de versionamento (secao 28): update() NUNCA sobrescreve o prompt
em vigor — sempre cria uma nova StrategyVersion e aponta
`current_version` para ela. delete() (secao 29) e' sempre soft-delete
(ARCHIVED), o historico de versoes e execucoes nunca e apagado.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from alphaquant_core.strategies.strategy_parser import StrategyPrompt, parse_prompt
from alphaquant_core.strategies.strategy_validator import ValidationResult, validate_prompt


class StrategyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


@dataclass
class StrategyVersion:
    version_id: str
    version_label: str          # "v1", "v2", ...
    prompt_raw: str
    parsed: StrategyPrompt | None
    validation: ValidationResult
    created_at: datetime
    author: str | None = None
    change_note: str | None = None

    def to_dict(self) -> dict:
        return {
            "version_id": self.version_id,
            "version_label": self.version_label,
            "prompt_raw": self.prompt_raw,
            "status": self.validation.status,
            "errors": self.validation.errors,
            "unsupported_conditions": self.validation.unsupported_conditions,
            "created_at": self.created_at.isoformat(),
            "author": self.author,
            "change_note": self.change_note,
        }


@dataclass
class StrategyDefinition:
    strategy_id: str
    name: str
    mode: str
    status: StrategyStatus
    versions: list[StrategyVersion] = field(default_factory=list)
    current_version_index: int = -1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def current_version(self) -> StrategyVersion:
        return self.versions[self.current_version_index]

    @property
    def is_runnable(self) -> bool:
        return self.status == StrategyStatus.ACTIVE and self.current_version.validation.valid

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "mode": self.mode,
            "status": self.status.value,
            "current_version": self.current_version.to_dict(),
            "version_count": len(self.versions),
            "is_runnable": self.is_runnable,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class StrategyRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._strategies: dict[str, StrategyDefinition] = {}

    def create(
        self, name: str, prompt_raw: str, mode: str = "SCANNER",
        active: bool = True, author: str | None = None,
    ) -> StrategyDefinition:
        version = self._build_version(name, prompt_raw, version_label="v1", author=author)
        strategy = StrategyDefinition(
            strategy_id=str(uuid.uuid4()),
            name=version.parsed.name if version.parsed else name,
            mode=mode,
            status=StrategyStatus.ACTIVE if active else StrategyStatus.INACTIVE,
            versions=[version],
            current_version_index=0,
        )
        with self._lock:
            self._strategies[strategy.strategy_id] = strategy
        return strategy

    def update(
        self, strategy_id: str, prompt_raw: str | None = None,
        mode: str | None = None, author: str | None = None,
        change_note: str | None = None,
    ) -> StrategyDefinition:
        """Cria uma NOVA versao — nunca sobrescreve a atual (secao 28)."""
        strategy = self._require(strategy_id)
        with self._lock:
            if prompt_raw is not None:
                label = f"v{len(strategy.versions) + 1}"
                version = self._build_version(
                    strategy.name, prompt_raw, version_label=label,
                    author=author, change_note=change_note,
                )
                strategy.versions.append(version)
                strategy.current_version_index = len(strategy.versions) - 1
                if version.parsed:
                    strategy.name = version.parsed.name
            if mode is not None:
                strategy.mode = mode
            strategy.updated_at = datetime.now(timezone.utc)
        return strategy

    def set_status(self, strategy_id: str, status: StrategyStatus) -> StrategyDefinition:
        strategy = self._require(strategy_id)
        with self._lock:
            strategy.status = status
            strategy.updated_at = datetime.now(timezone.utc)
        return strategy

    def activate(self, strategy_id: str) -> StrategyDefinition:
        return self.set_status(strategy_id, StrategyStatus.ACTIVE)

    def deactivate(self, strategy_id: str) -> StrategyDefinition:
        return self.set_status(strategy_id, StrategyStatus.INACTIVE)

    def archive(self, strategy_id: str) -> StrategyDefinition:
        """DELETAR == ARCHIVE (secao 29) — historico nunca e apagado."""
        return self.set_status(strategy_id, StrategyStatus.ARCHIVED)

    def duplicate(self, strategy_id: str, new_name: str | None = None) -> StrategyDefinition:
        source = self._require(strategy_id)
        current = source.current_version
        name = new_name or f"{source.name} (copia)"
        return self.create(name=name, prompt_raw=current.prompt_raw, mode=source.mode, active=False)

    def get(self, strategy_id: str) -> StrategyDefinition:
        return self._require(strategy_id)

    def list(self, status: StrategyStatus | None = None) -> list[StrategyDefinition]:
        values = list(self._strategies.values())
        if status is not None:
            values = [s for s in values if s.status == status]
        return sorted(values, key=lambda s: s.created_at)

    def list_active_runnable(self) -> list[StrategyDefinition]:
        return [s for s in self.list(StrategyStatus.ACTIVE) if s.is_runnable]

    def _require(self, strategy_id: str) -> StrategyDefinition:
        with self._lock:
            strategy = self._strategies.get(strategy_id)
        if strategy is None:
            raise KeyError(f"estrategia nao encontrada: {strategy_id}")
        return strategy

    @staticmethod
    def _build_version(
        name: str, prompt_raw: str, version_label: str,
        author: str | None = None, change_note: str | None = None,
    ) -> StrategyVersion:
        parsed: StrategyPrompt | None = None
        try:
            parsed = parse_prompt(name, prompt_raw)
            validation = validate_prompt(parsed)
        except Exception as exc:  # ParseError ou qualquer erro de parsing inesperado
            validation = ValidationResult(valid=False, errors=[str(exc)])

        return StrategyVersion(
            version_id=str(uuid.uuid4()),
            version_label=version_label,
            prompt_raw=prompt_raw,
            parsed=parsed,
            validation=validation,
            created_at=datetime.now(timezone.utc),
            author=author,
            change_note=change_note,
        )
