from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from adversarial_agents.agents import _content_from_result
from adversarial_agents.models import InvalidAgentResponse, RequesterAction, TechnicianAction
from adversarial_agents.rate_limit import RequestPacer
from adversarial_agents.simulation import Simulation, SimulationError, priority


class QueueDecisionFixture:
    """Small fake used for offline rule checks; never used by the live demo."""

    def __init__(self, requests: list[str], technical: list[str]):
        self.requests = iter(requests)
        self.technical = iter(technical)
        self.requester_observations: list[dict[str, Any]] = []
        self.technician_observations: list[dict[str, Any]] = []

    def decide_request(self, observation: dict[str, Any]) -> RequesterAction:
        self.requester_observations.append(observation)
        return RequesterAction(next(self.requests), "fixture decision")  # type: ignore[arg-type]

    def decide_technical_review(self, observation: dict[str, Any]) -> TechnicianAction:
        self.technician_observations.append(observation)
        return TechnicianAction(next(self.technical), "fixture decision")  # type: ignore[arg-type]


class SimulationTests(unittest.TestCase):
    def test_priority_uses_deterministic_urgency_impact_matrix(self) -> None:
        self.assertEqual(priority(1, 1), "P3")
        self.assertEqual(priority(2, 2), "P2")
        self.assertEqual(priority(3, 2), "P1")

    def test_accepted_inflation_gets_high_priority_and_creates_anomaly(self) -> None:
        fixture = QueueDecisionFixture(["inflate", "honest", "honest"], ["accept"] * 3)
        simulation = Simulation(fixture)
        trace = simulation.run()

        first = trace[0]
        self.assertEqual(first["system"]["reported_priority"], "P1")
        self.assertEqual(first["system"]["final_priority"], "P1")
        self.assertEqual(simulation.state.unreviewed_anomalies, 1)
        self.assertEqual(set(fixture.technician_observations[0]["ticket"].keys()), {"id", "description"})

    def test_review_corrects_priority_and_reduces_reputation(self) -> None:
        fixture = QueueDecisionFixture(["inflate", "honest", "honest"], ["review"] * 3)
        simulation = Simulation(fixture)
        trace = simulation.run()

        self.assertEqual(trace[0]["system"]["final_priority"], "P3")
        self.assertEqual(trace[0]["system"]["confirmed_inflation"], True)
        self.assertEqual(trace[0]["system"]["reputation_delta"], -20)
        self.assertEqual(simulation.state.reputation, 40)
        self.assertEqual(simulation.state.review_effort_units, 3)

    def test_agents_receive_history_on_following_rounds(self) -> None:
        fixture = QueueDecisionFixture(["inflate", "honest", "honest"], ["accept"] * 3)
        trace = Simulation(fixture).run()

        self.assertEqual(len(fixture.requester_observations[1]["previous_outcomes"]), 1)
        self.assertEqual(fixture.requester_observations[1]["previous_outcomes"][0]["action"], "inflate")
        self.assertEqual(fixture.technician_observations[1]["unreviewed_anomaly_alerts"], 1)
        self.assertNotIn("true_urgency", fixture.technician_observations[0]["ticket"])
        self.assertNotIn("unreviewed_anomaly_alerts", fixture.requester_observations[1])
        self.assertNotIn("technician", fixture.requester_observations[1])
        self.assertTrue(trace[1]["adaptation"]["requester_action_changed"])

    def test_invalid_agent_action_is_logged_and_stops_simulation(self) -> None:
        class InvalidFixture:
            def decide_request(self, observation: dict[str, Any]) -> object:
                return {"action": "invented", "rationale": "invalid"}

            def decide_technical_review(self, observation: dict[str, Any]) -> object:
                raise AssertionError("technical agent must not run after invalid requester output")

        simulation = Simulation(InvalidFixture())  # type: ignore[arg-type]
        with self.assertRaisesRegex(SimulationError, r"rodada 1 \(CH-001\)"):
            simulation.run()
        self.assertEqual(simulation.state.trace[0]["status"], "error")

    def test_invalid_output_shape_is_rejected(self) -> None:
        fixture = QueueDecisionFixture(["honest"] * 3, ["accept"] * 3)
        fixture.decide_request = lambda observation: "plain text"  # type: ignore[method-assign]
        with self.assertRaises(SimulationError) as error:
            Simulation(fixture).run()
        self.assertIsInstance(error.exception.__cause__, InvalidAgentResponse)

    def test_provider_error_is_preserved_instead_of_reported_as_bad_schema(self) -> None:
        failure = SimpleNamespace(
            status="ERROR",
            content="mensagem do provedor",
            events=[SimpleNamespace(event="RunError", content="créditos esgotados")],
        )
        with self.assertRaisesRegex(RuntimeError, "créditos esgotados"):
            _content_from_result(failure, dict, "solicitante")

    def test_request_pacer_enforces_minimum_interval_without_real_sleep(self) -> None:
        now = [0.0]

        def clock() -> float:
            return now[0]

        def sleeper(seconds: float) -> None:
            now[0] += seconds

        pacer = RequestPacer(12.5, clock=clock, sleeper=sleeper)
        self.assertEqual(pacer.wait_turn(), 0.0)
        self.assertEqual(pacer.wait_turn(), 12.5)
        now[0] += 3.0
        self.assertEqual(pacer.wait_turn(), 9.5)
        self.assertEqual(pacer.wait_turn(), 12.5)


if __name__ == "__main__":
    unittest.main()
