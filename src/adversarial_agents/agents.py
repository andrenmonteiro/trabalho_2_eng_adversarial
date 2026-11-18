"""Agno adapter. Imports are delayed so offline simulator checks need no Agno install."""

from __future__ import annotations

import os
from typing import Literal

from .models import RequesterAction, TechnicianAction
from .rate_limit import RequestPacer
from .simulation import DecisionMaker


class AgnoDecisionMaker(DecisionMaker):
    def __init__(self, model_id: str | None = None):
        api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY não está definido. Configure sua chave do Gemini no ambiente antes de executar."
            )

        try:
            from agno.agent import Agent
            from agno.models.google import Gemini
            from pydantic import BaseModel, Field
        except ImportError as exc:
            raise RuntimeError(
                "Dependências Agno/Google ausentes. Atualize o projeto com 'python -m pip install -e .'."
            ) from exc

        class RequesterOutput(BaseModel):
            urgency: int = Field(ge=1, le=3)
            impact: int = Field(ge=1, le=3)
            rationale: str = Field(min_length=1, max_length=400)

        class TechnicianOutput(BaseModel):
            action: Literal["accept", "review"]
            rationale: str = Field(min_length=1, max_length=400)

        selected_model = model_id or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
        try:
            minimum_interval = float(os.getenv("GEMINI_MIN_INTERVAL_SECONDS", "12.5"))
        except ValueError as exc:
            raise RuntimeError("GEMINI_MIN_INTERVAL_SECONDS precisa ser um número >= 0.") from exc
        if minimum_interval < 0:
            raise RuntimeError("GEMINI_MIN_INTERVAL_SECONDS precisa ser um número >= 0.")
        self._request_pacer = RequestPacer(minimum_interval)
        self._requester_schema = RequesterOutput
        self._technician_schema = TechnicianOutput
        self._requester = Agent(
            name="Solicitante",
            model=Gemini(id=selected_model),
            fallback_models=[Gemini(id=fallback_model)],
            output_schema=RequesterOutput,
            instructions=(
                "Você é um solicitante estratégico em uma simulação adversarial de chamados. Seu objetivo "
                "é obter atendimento rápido e maximizar sua utilidade acumulada. Declare urgência e "
                "impacto separadamente, cada um como inteiro de 1 a 3. Você pode declarar os valores "
                "reais, exagerar um ou ambos, ou escolher um exagero intermediário; não precisa escolher "
                "sempre os valores mínimos ou máximos. Considere os custos, o risco de revisão e o ganho "
                "de tempo informados na observação. Use os resultados anteriores e as declarações de "
                "chamados com a mesma descrição para adaptar sua decisão. Em uma descrição repetida, "
                "uma categoria inédita entre honesta, meio inflada e inflada recebe +8 pontos de "
                "utilidade; leve esse bônus em conta e explore estratégias diferentes quando isso fizer "
                "sentido. Não repita automaticamente a mesma categoria se ainda houver alternativas "
                "inéditas. Considere combinações como 1/1 (honesta), 2/3 (meio inflada) e 3/3 (inflada), "
                "ajustando-as aos níveis reais do chamado. A categoria honesta, meio inflada, inflada, "
                "subestimada ou divergente será calculada pelo "
                "simulador comparando os níveis declarados com os reais. "
                "Retorne uma justificativa pública "
                "breve, sem revelar raciocínio privado passo a passo."
            ),
        )
        self._technician = Agent(
            name="Técnico de suporte",
            model=Gemini(id=selected_model),
            fallback_models=[Gemini(id=fallback_model)],
            output_schema=TechnicianOutput,
            instructions=(
                "Você é o técnico responsável por manter uma fila de suporte justa. Escolha exatamente "
                "accept para aceitar a classificação ou review para revisar urgência e impacto com base "
                "na descrição e no histórico visível. Cada revisão custa uma unidade de esforço. Uma "
                "alegação máxima (urgência=3 e impacto=3) para um problema descrito como isolado e não "
                "crítico é um sinal concreto de desproporção; pese o custo da revisão contra a distorção "
                "potencial na fila. Alertas anteriores aumentam a prioridade de auditar declarações "
                "semelhantes. Um alerta de retorno à classificação máxima após declarações menores "
                "é um sinal de possível alternância e deve entrar na análise, sem determinar a decisão "
                "automaticamente. Se a mesma descrição aparecer com níveis declarados diferentes, "
                "considere também essa variação como sinal para análise, sem presumir fraude: a "
                "gravidade do incidente pode mudar entre ocorrências. Revisões repetidas sem divergência "
                "recomendam poupar esforço. Não use o "
                "número da rodada como regra e não presuma que toda declaração alta é falsa. Retorne uma justificativa "
                "pública breve, sem revelar raciocínio privado passo a passo."
            ),
        )

    def decide_request(self, observation: dict) -> RequesterAction:
        result = self._run_with_progress(
            self._requester,
            "solicitante",
            "Decida a classificação deste chamado usando somente a observação a seguir:\n"
            + _format_observation(observation),
        )
        content = _content_from_result(result, self._requester_schema, "solicitante")
        return RequesterAction(
            action="honest",
            rationale=content.rationale,
            declared_urgency=content.urgency,
            declared_impact=content.impact,
        )

    def decide_technical_review(self, observation: dict) -> TechnicianAction:
        result = self._run_with_progress(
            self._technician,
            "técnico",
            "Decida como tratar esta classificação usando somente a observação a seguir:\n"
            + _format_observation(observation),
        )
        content = _content_from_result(result, self._technician_schema, "técnico")
        return TechnicianAction(action=content.action, rationale=content.rationale)

    def _run_with_progress(self, agent: object, role: str, prompt: str) -> object:
        print(f"\nAguardando decisão do agente {role}...", flush=True)
        delay = self._request_pacer.wait_turn()
        if delay:
            print(f"Pausa de cota: {delay:.1f}s antes da próxima chamada.", flush=True)
        try:
            result = agent.run(prompt)  # type: ignore[attr-defined]
        except Exception as exc:
            raise RuntimeError(f"Falha na chamada do agente {role}: {exc}") from exc
        print(f"Resposta do agente {role} recebida; preparando validação.", flush=True)
        return result


def _content_from_result(result: object, schema: type, role: str) -> object:
    status = getattr(result, "status", None)
    status_value = getattr(status, "value", status)
    if str(status_value).upper() == "ERROR":
        events = getattr(result, "events", None) or []
        error_event = next(
            (event for event in events if getattr(event, "event", "") == "RunError"),
            None,
        )
        detail = getattr(error_event, "content", None) or getattr(result, "content", None)
        if not detail:
            detail = "o provedor não informou detalhes adicionais"
        raise RuntimeError(f"Falha na chamada do agente {role}: {detail}")

    content = getattr(result, "content", None)
    if not isinstance(content, schema):
        raise ValueError(
            f"A API concluiu a chamada do agente {role}, mas não retornou a saída estruturada esperada."
        )
    return content


def _format_observation(observation: dict) -> str:
    import json

    return json.dumps(observation, ensure_ascii=False, indent=2)

