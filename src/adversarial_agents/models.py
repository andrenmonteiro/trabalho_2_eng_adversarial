"""Small, dependency-free data types used by the game simulator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

Level = Literal[1, 2, 3]


@dataclass(frozen=True)
class RequesterAction:
    action: Literal["honest", "moderate_inflate", "inflate", "understate", "misstate"]
    rationale: str
    declared_urgency: int | None = None
    declared_impact: int | None = None


@dataclass(frozen=True)
class TechnicianAction:
    action: Literal["accept", "review"]
    rationale: str


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    description: str
    true_urgency: Level
    true_impact: Level


class InvalidAgentResponse(ValueError):
    """Raised when an agent returns an unsupported or incomplete decision."""


def requester_action_from(value: object) -> RequesterAction:
    if isinstance(value, RequesterAction):
        result = value
    elif isinstance(value, Mapping):
        result = RequesterAction(
            action=value.get("action"),  # type: ignore[arg-type]
            rationale=value.get("rationale"),  # type: ignore[arg-type]
            declared_urgency=value.get("declared_urgency"),  # type: ignore[arg-type]
            declared_impact=value.get("declared_impact"),  # type: ignore[arg-type]
        )
    else:
        raise InvalidAgentResponse("A resposta do solicitante não é um objeto estruturado.")

    if result.action not in ("honest", "moderate_inflate", "inflate", "understate", "misstate"):
        raise InvalidAgentResponse("Categoria de declaração do solicitante inválida.")
    if (result.declared_urgency is None) != (result.declared_impact is None):
        raise InvalidAgentResponse("Urgência e impacto declarados precisam ser informados juntos.")
    if result.declared_urgency is not None:
        _validate_level(result.declared_urgency, "urgência")
        _validate_level(result.declared_impact, "impacto")
    _validate_rationale(result.rationale)
    return result


def technician_action_from(value: object) -> TechnicianAction:
    if isinstance(value, TechnicianAction):
        result = value
    elif isinstance(value, Mapping):
        result = TechnicianAction(
            action=value.get("action"),  # type: ignore[arg-type]
            rationale=value.get("rationale"),  # type: ignore[arg-type]
        )
    else:
        raise InvalidAgentResponse("A resposta do técnico não é um objeto estruturado.")

    if result.action not in ("accept", "review"):
        raise InvalidAgentResponse("Ação do técnico inválida; use 'accept' ou 'review'.")
    _validate_rationale(result.rationale)
    return result


def _validate_rationale(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidAgentResponse("Toda decisão precisa incluir uma justificativa curta.")


def _validate_level(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value not in (1, 2, 3):
        raise InvalidAgentResponse(f"{label.capitalize()} declarada precisa ser 1, 2 ou 3.")

