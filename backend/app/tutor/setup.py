"""The set-up step: name the problem's concept and write its hidden worked solution."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.ai_gateway import gateway
from app.ai_gateway.schema import GatewayFallback, GatewayOk
from app.history import HistoryStore

INSTRUCTIONS = (Path(__file__).parent / "setup_prompt.txt").read_text(encoding="utf-8")


class SetupOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_name: str = Field(min_length=1, max_length=80)
    result: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1)


setup_agent = Agent(
    output_type=SetupOutput,
    instructions=INSTRUCTIONS,
    retries=1,
    model_settings={"temperature": 0},
    name="tutor_setup",
)


def known_concepts(store: HistoryStore) -> list[str]:
    """Concept names already tracked for any learner, read through the history interface."""
    names = set()
    for student in store.list_students():
        for state in store.list_concept_states(student.id):
            concept = store.get_concept(state.concept_id)
            if concept is not None:
                names.add(concept.name)
    return sorted(names)


async def solve(
    problem: str, subject: str | None, store: HistoryStore, model: Model,
    timeout: float = gateway.DEFAULT_TIMEOUT_SECONDS,
) -> GatewayOk[SetupOutput] | GatewayFallback[SetupOutput]:
    import json

    prompt = json.dumps({"problem": problem, "subject": subject, "known_concepts": known_concepts(store)}, indent=2)
    unsolved = SetupOutput(concept_name="unknown", result="unknown", steps=["unknown"])
    return await gateway.call(setup_agent, prompt, model=model, fallback=unsolved, timeout=timeout)
