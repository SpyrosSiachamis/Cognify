"""The set-up step: name the problem's concept and write its hidden worked solution."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from app.ai_gateway import gateway
from app.ai_gateway.schema import GatewayFallback, GatewayOk
from app.history import HistoryStore

from .evidence import numeric_values
from .expected_check import ExpectedCheck, check_expected

INSTRUCTIONS = (Path(__file__).parent / "setup_prompt.txt").read_text(encoding="utf-8")


class SetupOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_name: str = Field(min_length=1, max_length=80)
    # The steps come before the result, so the model works the answer out before it states it (a result written
    # first was often a guess the steps then contradicted, and that guess became the hidden solution).
    steps: list[str] = Field(min_length=1)
    result: str = Field(min_length=1)
    # The answer as values and conditions, for code's check (expected_check.py); null when the problem has none.
    expected_check: ExpectedCheck | None = None


setup_agent = Agent(
    output_type=SetupOutput,
    deps_type=str,  # the problem text, for code's check of the expected solution
    instructions=INSTRUCTIONS,
    retries=1,
    model_settings={"temperature": 0},
    name="tutor_setup",
)

def result_matches_steps(output: SetupOutput) -> bool:
    """Code check: a numeric result must be a value the last step reaches (non-numeric results are not checked)."""
    result = numeric_values(output.result)
    return not result or bool(result & numeric_values(output.steps[-1]))


@setup_agent.output_validator
def _check_result(ctx: RunContext[str], output: SetupOutput) -> SetupOutput:
    if not result_matches_steps(output):
        raise ModelRetry(
            "Your result does not match the value your last step reaches. Work the steps out, end them at the "
            "answer, and give that same value as the result."
        )
    # An answer code proves wrong is never kept: the model solves again (no retry left: no solution, never this one).
    verdict = check_expected(output.expected_check, ctx.deps or "", output.result)
    if verdict.status == "INVALID_EXPECTED_SOLUTION":
        raise ModelRetry(
            f"Your answer does not satisfy the problem: {verdict.reason}. Solve the problem again from its conditions "
            "and give exact values (for example 1 + sqrt(61), not 8.81)."
        )
    return output


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
    return await gateway.call(setup_agent, prompt, model=model, deps=problem, fallback=unsolved, timeout=timeout)
