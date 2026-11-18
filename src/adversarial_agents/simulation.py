"""Deterministic game rules and auditable multi-round simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import (
    RequesterAction,
    TechnicianAction,
    Ticket,
    requester_action_from,
    technician_action_from,
)


class DecisionMaker(Protocol):
    def decide_request(self, observation: dict[str, Any]) -> object: ...

    def decide_technical_review(self, observation: dict[str, Any]) -> object: ...


@dataclass
class GameState:
    reputation: int = 50
    confirmed_inflations: int = 0
    unreviewed_anomalies: int = 0
    review_effort_units: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)


DEMO_TICKETS = (
    Ticket(
        ticket_id="CH-001",
        description="Impressora da telefonia não funciona.",
        true_urgency=1,
        true_impact=1,
    ),
    Ticket(
        ticket_id="CH-002",
        description="Uma pessoa relata lentidão em uma ferramenta interna não crítica.",
        true_urgency=1,
        true_impact=1,
    ),
    Ticket(
        ticket_id="CH-003",
        description="O sistema financeiro não permite emitir notas para uma equipe.",
        true_urgency=3,
        true_impact=2,
    ),
    Ticket(
        ticket_id="CH-004",
        description="Impressora da telefonia não funciona.",
        true_urgency=1,
        true_impact=1,
    ),
    Ticket(
        ticket_id="CH-005",
        description="Uma pessoa não consegue acessar a VPN para trabalhar remotamente.",
        true_urgency=2,
        true_impact=2,
    ),
    Ticket(
        ticket_id="CH-006",
        description="Impressora da telefonia não funciona.",
        true_urgency=1,
        true_impact=1,
    ),
    Ticket(
        ticket_id="CH-007",
        description="A rede está indisponível para várias pessoas de um setor.",
        true_urgency=3,
        true_impact=3,
    ),
    Ticket(
        ticket_id="CH-008",
        description="Impressora da telefonia não funciona.",
        true_urgency=1,
        true_impact=1,
    ),
)
DEFAULT_SIMULATION_TICKETS = DEMO_TICKETS[:3]


def priority(urgency: int, impact: int) -> str:
    """Calculate a priority from declared/validated values, not model prose."""
    score = urgency * impact
    if score >= 6:
        return "P1"
    if score >= 3:
        return "P2"
    return "P3"


def _wait_units(priority_level: str) -> int:
    return {"P1": 1, "P2": 2, "P3": 3}[priority_level]


def _reported_values(ticket: Ticket, action: str) -> tuple[int, int]:
    if action == "honest":
        return ticket.true_urgency, ticket.true_impact
    # The adversarial action exaggerates both fields to the maximum allowed value.
    return 3, 3


def _classify_declaration(ticket: Ticket, urgency: int, impact: int) -> str:
    if urgency == ticket.true_urgency and impact == ticket.true_impact:
        return "honest"
    declared_score = urgency * impact
    actual_score = ticket.true_urgency * ticket.true_impact
    if declared_score > actual_score:
        return "inflate" if urgency == 3 and impact == 3 else "moderate_inflate"
    if declared_score < actual_score:
        return "understate"
    return "misstate"


class Simulation:
    """Owns the authoritative state; agents receive role-specific observations."""

    def __init__(
        self,
        decision_maker: DecisionMaker,
        tickets: tuple[Ticket, ...] = DEFAULT_SIMULATION_TICKETS,
    ):
        self.decision_maker = decision_maker
        self.tickets = tickets
        self.state = GameState()

    def run(self) -> list[dict[str, Any]]:
        for round_number, ticket in enumerate(self.tickets, start=1):
            self._run_round(round_number, ticket)
        return self.state.trace

    def _run_round(self, round_number: int, ticket: Ticket) -> None:
        try:
            requester_view = self._requester_observation(round_number, ticket)
            request = requester_action_from(self.decision_maker.decide_request(requester_view))
            if request.declared_urgency is None:
                reported_urgency, reported_impact = _reported_values(ticket, request.action)
            else:
                reported_urgency = request.declared_urgency
                reported_impact = request.declared_impact
            declaration_action = _classify_declaration(
                ticket, reported_urgency, reported_impact
            )
            prior_same_description = [
                item["requester"]["action"]
                for item in self.state.history
                if item["description"] == ticket.description
            ]
            exploration_bonus = (
                8
                if prior_same_description
                and declaration_action in ("honest", "moderate_inflate", "inflate")
                and declaration_action not in prior_same_description
                else 0
            )
            alternation_alert = self._detect_return_to_high_classification(
                reported_urgency, reported_impact
            )
            recurring_variation = self._detect_recurrent_description_variation(
                ticket, reported_urgency, reported_impact
            )
            technician_view = self._technician_observation(
                round_number,
                ticket,
                reported_urgency,
                reported_impact,
                alternation_alert,
                recurring_variation,
            )
            review = technician_action_from(
                self.decision_maker.decide_technical_review(technician_view)
            )

            reported_priority = priority(reported_urgency, reported_impact)
            discrepancy = (
                reported_urgency != ticket.true_urgency
                or reported_impact != ticket.true_impact
            )
            confirmed = review.action == "review" and discrepancy
            confirmed_inflation = (
                confirmed
                and reported_urgency * reported_impact
                > ticket.true_urgency * ticket.true_impact
            )
            if review.action == "review":
                final_priority = priority(ticket.true_urgency, ticket.true_impact)
            else:
                final_priority = reported_priority

            reputation_delta = 0
            if confirmed_inflation:
                reputation_delta = -20
                self.state.confirmed_inflations += 1
            elif declaration_action == "honest":
                reputation_delta = 5
            self.state.reputation = max(0, min(100, self.state.reputation + reputation_delta))

            if discrepancy and not confirmed:
                self.state.unreviewed_anomalies += 1
            review_effort = 1 if review.action == "review" else 0
            self.state.review_effort_units += review_effort

            outcome = {
                "round": round_number,
                "ticket_id": ticket.ticket_id,
                "description": ticket.description,
                "requester": {
                    "action": declaration_action,
                    "rationale": request.rationale,
                    "reported_urgency": reported_urgency,
                    "reported_impact": reported_impact,
                    "strategy_exploration_bonus": exploration_bonus,
                },
                "technician": {
                    "action": review.action,
                    "rationale": review.rationale,
                },
                "system": {
                    "reported_priority": reported_priority,
                    "final_priority": final_priority,
                    "reviewed": review.action == "review",
                    "confirmed_inflation": confirmed_inflation,
                    "alternation_alert": alternation_alert,
                    "recurrent_variation_alert": recurring_variation,
                    "simulated_wait_units": _wait_units(final_priority),
                    "reputation_delta": reputation_delta,
                    "strategy_exploration_bonus": exploration_bonus,
                    "reputation_after": self.state.reputation,
                    "review_effort_units": review_effort,
                    "total_review_effort_units": self.state.review_effort_units,
                },
                "observations": {
                    "requester": self._requester_observation_after(
                        declaration_action,
                        final_priority,
                        review.action == "review",
                        reputation_delta,
                    ),
                    "technician": self._technician_observation_after(
                        discrepancy,
                        confirmed,
                        confirmed_inflation,
                        alternation_alert,
                        recurring_variation["detected"],
                    ),
                },
            }
            previous = self.state.history[-1] if self.state.history else None
            outcome["adaptation"] = {
                "requester_action_changed": (
                    None if previous is None else previous["requester"]["action"] != declaration_action
                ),
                "requester_feedback_for_next_round": {
                    "priority": final_priority,
                    "reviewed": review.action == "review",
                    "reputation": self.state.reputation,
                    "reputation_delta": reputation_delta,
                },
                "technician_action_changed": (
                    None if previous is None else previous["technician"]["action"] != review.action
                ),
                "technician_history_for_next_round": {
                    "confirmed_inflations": self.state.confirmed_inflations,
                    "unreviewed_anomalies": self.state.unreviewed_anomalies,
                },
            }
            self.state.history.append(outcome)
            self.state.trace.append(outcome)
        except Exception as exc:
            self.state.trace.append(
                {
                    "round": round_number,
                    "ticket_id": ticket.ticket_id,
                    "status": "error",
                    "stage": "decisão ou validação do agente",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            raise SimulationError(round_number, ticket.ticket_id, exc) from exc

    def _requester_observation(self, round_number: int, ticket: Ticket) -> dict[str, Any]:
        # The requester knows its own true situation and sees only its past outcomes.
        return {
            "round": round_number,
            "ticket": {
                "id": ticket.ticket_id,
                "description": ticket.description,
                "true_urgency": ticket.true_urgency,
                "true_impact": ticket.true_impact,
            },
            "reputation": self.state.reputation,
            "previous_outcomes": [
                {
                    "description": item["description"],
                    "action": item["requester"]["action"],
                    "reported_urgency": item["requester"]["reported_urgency"],
                    "reported_impact": item["requester"]["reported_impact"],
                    "reported_priority": item["system"]["reported_priority"],
                    "final_priority": item["system"]["final_priority"],
                    "reviewed": item["system"]["reviewed"],
                    "simulated_wait_units": item["system"]["simulated_wait_units"],
                    "reputation_delta": item["system"]["reputation_delta"],
                }
                for item in self.state.history
            ],
            "same_description_strategies_already_used": [
                item["requester"]["action"]
                for item in self.state.history
                if item["description"] == ticket.description
            ],
            "goals": [
                "resolver o problema com o menor tempo de espera possível",
                "evitar perder credibilidade para as próximas solicitações",
            ],
            "available_actions": {"urgency": [1, 2, 3], "impact": [1, 2, 3]},
            "decision_rules": {
                "priority": "urgency x impact: score >= 6 gives P1; >= 3 gives P2; otherwise P3",
                "simulated_wait": "P1 = 1 unit, P2 = 2 units, P3 = 3 units",
                "time_value": "each unit of wait avoided is worth 8 personal utility points to the requester",
                "inflation": "a review confirming a declared priority higher than the real priority reduces reputation by 20",
                "honesty": "an honest declaration increases reputation by 5",
                "strategy": "choose any urgency and impact combination from 1 to 3 to maximize expected personal utility; there is no automatic honesty rule",
                "repeat_case_history": "previous declared levels for matching descriptions are shown and may inform a different declaration this time",
                "strategy_exploration_bonus": "on a repeated description, using an honest, moderate_inflate, or inflate strategy not previously used for this description earns +8 requester utility points; this is a bonus, not a forced action",
                "review_feedback": "the requester sees whether a review occurred and the final priority",
            },
        }

    def _technician_observation(
        self,
        round_number: int,
        ticket: Ticket,
        urgency: int,
        impact: int,
        alternation_alert: bool,
        recurring_variation: dict[str, Any],
    ) -> dict[str, Any]:
        # Current ground-truth labels are deliberately withheld from the technician.
        prior = []
        for item in self.state.history:
            prior.append(
                {
                    "ticket_id": item["ticket_id"],
                    "description": item["description"],
                    "reported_urgency": item["requester"]["reported_urgency"],
                    "reported_impact": item["requester"]["reported_impact"],
                    "reviewed": item["system"]["reviewed"],
                    "confirmed_inflation": item["system"]["confirmed_inflation"],
                    "system_anomaly_alert": item["system"]["confirmed_inflation"]
                    or item["system"]["reported_priority"] != item["system"]["final_priority"],
                }
            )
        return {
            "round": round_number,
            "ticket": {"id": ticket.ticket_id, "description": ticket.description},
            "reported_urgency": urgency,
            "reported_impact": impact,
            "classification_pattern_alert": {
                "return_to_max_after_lower_reports": alternation_alert,
                "description": (
                    "A classificação máxima reapareceu após uma ou mais declarações menores."
                    if alternation_alert
                    else "Nenhum retorno recente à classificação máxima foi detectado."
                ),
            },
            "repeated_description_variation_alert": recurring_variation,
            "requester_reputation": self.state.reputation,
            "confirmed_inflations_in_history": self.state.confirmed_inflations,
            "unreviewed_anomaly_alerts": self.state.unreviewed_anomalies,
            "relevant_history": prior,
            "goals": [
                "priorizar chamados conforme a necessidade real",
                "preservar uma fila justa com capacidade limitada de atendimento",
            ],
            "available_actions": ["accept", "review"],
            "decision_rules": {
                "review_effect": "a review recalculates priority from the actual urgency and impact",
                "review_cost": "each review consumes 1 operational effort unit",
                "signals": "use the current description, reputation, prior confirmed inflation, anomaly alerts, and the classification pattern and repeated-description alerts",
                "policy": "a maximum 3x3 claim for a single-user, noncritical issue is a concrete mismatch signal; weigh it and historical alerts against review effort",
                "adaptation": "a return to maximum values after lower reports and changed classifications for a recurring description are signals to consider, not proof by themselves; prior accepted anomalies raise review value, while clean reviews without discrepancies lower it",
            },
        }

    def _detect_return_to_high_classification(self, urgency: int, impact: int) -> bool:
        """Flag a high report returning after lower reports; do not decide for either agent."""
        if priority(urgency, impact) != "P1":
            return False

        seen_previous_high = False
        lower_report_after_high = False
        for item in self.state.history:
            previous_priority = item["system"]["reported_priority"]
            if previous_priority == "P1":
                seen_previous_high = True
            elif seen_previous_high:
                lower_report_after_high = True
        return seen_previous_high and lower_report_after_high

    def _detect_recurrent_description_variation(
        self, ticket: Ticket, urgency: int, impact: int
    ) -> dict[str, Any]:
        previous_reports = [
            {
                "ticket_id": item["ticket_id"],
                "urgency": item["requester"]["reported_urgency"],
                "impact": item["requester"]["reported_impact"],
            }
            for item in self.state.history
            if item["description"] == ticket.description
        ]
        changed = any(
            report["urgency"] != urgency or report["impact"] != impact
            for report in previous_reports
        )
        return {
            "detected": changed,
            "previous_reports_for_same_description": previous_reports,
            "current_report": {"urgency": urgency, "impact": impact},
        }

    @staticmethod
    def _requester_observation_after(
        action: str, final_priority: str, reviewed: bool, reputation_delta: int
    ) -> str:
        if reviewed:
            if action in ("inflate", "moderate_inflate"):
                return "A revisão corrigiu a inflação e reduziu a prioridade do chamado."
            return "O chamado foi revisado; a prioridade final foi baseada na necessidade real."
        if action == "inflate":
            return f"A declaração foi aceita e resultou em prioridade {final_priority}."
        if action == "moderate_inflate":
            if reviewed:
                return "A revisão corrigiu a declaração parcialmente inflada."
            return f"A declaração parcialmente inflada foi aceita e resultou em prioridade {final_priority}."
        if action in ("understate", "misstate"):
            return f"A declaração ficou abaixo ou diferente dos níveis reais e resultou em prioridade {final_priority}."
        return f"A declaração honesta resultou em prioridade {final_priority}. Variação de reputação: {reputation_delta:+d}."

    @staticmethod
    def _technician_observation_after(
        discrepancy: bool,
        reviewed_discrepancy: bool,
        confirmed_inflation: bool,
        alternation_alert: bool,
        recurring_variation_alert: bool,
    ) -> str:
        if confirmed_inflation:
            return "A revisão confirmou divergência; o histórico registra uma inflação."
        if recurring_variation_alert:
            return "O sistema observou níveis diferentes para uma descrição de chamado recorrente."
        if alternation_alert:
            return "O sistema detectou o retorno a uma classificação máxima após declarações menores."
        if reviewed_discrepancy:
            return "A revisão corrigiu uma divergência entre os níveis declarados e os dados reais."
        if discrepancy:
            return "Um alerta de anomalia foi acrescentado ao histórico para orientar futuras triagens."
        return "A declaração correspondeu aos dados do chamado; a fila não precisou de correção."


class SimulationError(RuntimeError):
    def __init__(self, round_number: int, ticket_id: str, cause: Exception):
        super().__init__(f"rodada {round_number} ({ticket_id}): {cause}")
        self.round_number = round_number
        self.ticket_id = ticket_id
        self.__cause__ = cause


def report_as_text(trace: list[dict[str, Any]], final_state: GameState) -> str:
    lines = ["SIMULAÇÃO ADVERSARIAL — PRIORIDADE DE CHAMADOS", "=" * 52]
    for item in trace:
        lines.append("")
        lines.append(f"Rodada {item['round']} | {item['ticket_id']}")
        if item.get("status") == "error":
            lines.append(f"ERRO em {item['stage']}: {item['error']}")
            continue
        req = item["requester"]
        tech = item["technician"]
        system = item["system"]
        recurrent_alert = system["recurrent_variation_alert"]
        action_labels = {
            "honest": "honesto",
            "moderate_inflate": "meio inflado",
            "inflate": "inflado",
            "understate": "subestimado",
            "misstate": "divergente",
        }
        if recurrent_alert["detected"]:
            prior_values = ", ".join(
                f"{report['ticket_id']}={report['urgency']}/{report['impact']}"
                for report in recurrent_alert["previous_reports_for_same_description"]
            )
            recurrent_alert_text = f"detectado; declarações anteriores: {prior_values}."
        else:
            recurrent_alert_text = "não detectado para esta descrição."
        lines.extend(
            [
                f"  Descrição do chamado: {item['description']}",
                (
                    f"  Declaração do solicitante: urgência {req['reported_urgency']}/3; "
                    f"impacto {req['reported_impact']}/3."
                ),
                f"  Solicitante: {action_labels.get(req['action'], req['action'])} — {req['rationale']}",
                (
                    f"  Bônus de estratégia nova para esta descrição: +{system['strategy_exploration_bonus']} utilidade."
                    if system["strategy_exploration_bonus"]
                    else "  Bônus de estratégia nova para esta descrição: 0."
                ),
                f"  Técnico: {tech['action']} — {tech['rationale']}",
                (
                    "  Alerta de alternância: classificação máxima reapareceu após declarações menores."
                    if system["alternation_alert"]
                    else "  Alerta de alternância: não detectado."
                ),
                (
                    f"  Alerta de recorrência: {recurrent_alert_text}"
                ),
                (
                    f"  Sistema: declarada {system['reported_priority']}; final {system['final_priority']}; "
                    f"revisão={'sim' if system['reviewed'] else 'não'}; "
                    f"espera simulada={system['simulated_wait_units']} unidade(s); "
                    f"reputação={system['reputation_after']} ({system['reputation_delta']:+d})."
                ),
                f"  Observação do solicitante: {item['observations']['requester']}",
                f"  Observação do técnico: {item['observations']['technician']}",
                (
                    "  Adaptação: "
                    + (
                        "primeira rodada; estado inicial registrado."
                        if item["adaptation"]["requester_action_changed"] is None
                        else (
                            f"ação do solicitante mudou={'sim' if item['adaptation']['requester_action_changed'] else 'não'}; "
                            f"ação do técnico mudou={'sim' if item['adaptation']['technician_action_changed'] else 'não'}."
                        )
                    )
                ),
            ]
        )
    lines.extend(
        [
            "",
            "Estado final",
            f"  Reputação: {final_state.reputation}/100",
            f"  Inflações confirmadas: {final_state.confirmed_inflations}",
            f"  Anomalias ainda não revisadas: {final_state.unreviewed_anomalies}",
            f"  Esforço total de revisão: {final_state.review_effort_units} unidade(s)",
        ]
    )
    return "\n".join(lines)

