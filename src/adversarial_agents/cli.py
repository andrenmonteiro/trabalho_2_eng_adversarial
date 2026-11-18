"""Command-line entry point for the live Agno demonstration."""

from __future__ import annotations

import os
import sys

from .agents import AgnoDecisionMaker
from .models import Ticket
from .simulation import Simulation, SimulationError, create_demo_tickets, report_as_text


def main() -> int:
    if not os.getenv("GOOGLE_API_KEY", "").strip():
        print(
            "Erro: defina GOOGLE_API_KEY antes de iniciar a demonstração.",
            file=sys.stderr,
        )
        return 2

    try:
        tickets = _choose_tickets()
        simulation = Simulation(AgnoDecisionMaker(), tickets=tickets)
    except Exception as exc:
        print(f"Erro ao inicializar os agentes: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        trace = simulation.run()
    except SimulationError as exc:
        print(report_as_text(simulation.state.trace, simulation.state), file=sys.stderr)
        print(f"\nExecução interrompida: {exc}", file=sys.stderr)
        return 1

    print(report_as_text(trace, simulation.state))
    return 0


def _choose_tickets() -> tuple[Ticket, ...]:
    print("SIMULAÇÃO DE PRIORIDADE DE CHAMADOS")
    print("1. Executar cenário padrão (8 chamados)")
    print("2. Informar um chamado manualmente")
    while True:
        choice = input("Escolha 1 ou 2: ").strip()
        if choice == "1":
            return create_demo_tickets()
        if choice == "2":
            description = input("Descreva o problema observado: ").strip()
            while not description:
                print("A descrição não pode ficar vazia.")
                description = input("Descreva o problema observado: ").strip()
            urgency = _read_level("Urgência real (1=baixa, 2=média, 3=alta): ")
            impact = _read_level("Impacto real (1=baixo, 2=médio, 3=alto): ")
            print(
                "\nO solicitante receberá a descrição e os níveis reais e escolherá urgência e impacto "
                "declarados entre 1 e 3. O técnico verá a descrição e os níveis declarados, "
                "mas não os níveis reais.\n"
            )
            return (Ticket("CH-MANUAL", description, urgency, impact),)
        print("Opção inválida. Digite 1 ou 2.")


def _read_level(prompt: str) -> int:
    while True:
        value = input(prompt).strip()
        if value in {"1", "2", "3"}:
            return int(value)
        print("Informe 1, 2 ou 3.")


if __name__ == "__main__":
    raise SystemExit(main())

