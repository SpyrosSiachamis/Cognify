"""The reasoning step: one structured call that diagnoses the student's work.

It sees only the problem, the attempt and the final answer: never the teaching
method or the history, so the diagnosis cannot bend toward how we will teach.
"""

import re
from pathlib import Path

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from app.ai_gateway import gateway
from app.ai_gateway.schema import GatewayFallback, GatewayOk

from .repair import GAP_STEPS
from .schema import ReasoningInput, Step, TutorDiagnosis

INSTRUCTIONS = (Path(__file__).parent / "reasoning_prompt.txt").read_text(encoding="utf-8")

reasoning_agent = Agent(
    output_type=TutorDiagnosis,
    deps_type=ReasoningInput,
    instructions=INSTRUCTIONS,
    retries=1,
    # Diagnosis should be repeatable, not creative.
    model_settings={"temperature": 0},
    name="tutor_reasoning",
)


def _normalise(text: str) -> str:
    text = text.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip(" .,;:!?\"'")


# Saying you do not know how to do a step is missing evidence, not a wrong step (English only for now).
NOT_KNOWING = re.compile(r"\b(i )?(do not|don't|dont) know\b|\bnot sure\b|\bno idea\b|\bi'?m stuck\b|\bcan'?t (figure|work) out\b", re.I)


def apply_rules(diagnosis: TutorDiagnosis, attempt: str, check_gap_step: bool = True) -> TutorDiagnosis:
    """Deterministic rules on top of the model's reading.

    - No quote, no claim (rule 7): a step whose quote is not in the attempt becomes missing.
    - A "wrong" step whose quote only says the student does not know is missing.
    - Every step missing: there is no evidence to diagnose (insufficient, low, no gap).
    - Every step correct: no demonstrated gap.
    """
    text = _normalise(attempt)
    steps = [
        s if not s.quote or _normalise(s.quote) in text else s.model_copy(update={"status": "missing", "quote": None})
        for s in diagnosis.steps
    ]
    steps = [
        s.model_copy(update={"status": "missing"}) if s.status == "wrong" and NOT_KNOWING.search(s.quote or "") else s
        for s in steps
    ]
    update: dict = {"steps": steps}
    if all(s.status == "missing" for s in steps):
        update |= {"evidence": "insufficient", "confidence": "low", "main_gap": None, "alternatives": []}
    elif all(s.status == "correct" for s in steps):
        update |= {"main_gap": None, "alternatives": []}
    result = TutorDiagnosis.model_validate(diagnosis.model_copy(update=update).model_dump())
    # A gap must show where that kind of gap lives (for example a recognition gap at choose_method).
    roles = GAP_STEPS.get(result.main_gap, ()) if result.main_gap and check_gap_step else ()
    if roles and any(s.role in roles and s.status == "correct" for s in result.steps) and not any(
        s.role in roles and s.status != "correct" for s in result.steps
    ):
        raise ValueError(
            f"main_gap is {result.main_gap}, but {' and '.join(roles)} is marked correct. A {result.main_gap} gap "
            f"shows at {' or '.join(roles)}: mark that step wrong or missing, or choose the main gap that "
            "matches the step that actually fails"
        )
    return result


@reasoning_agent.output_validator
def follow_the_rules(ctx: RunContext[ReasoningInput], output: TutorDiagnosis) -> TutorDiagnosis:
    try:
        # The gap-step consistency check asks once; a second disagreement is accepted rather than
        # throwing the whole diagnosis away.
        return apply_rules(output, ctx.deps.attempt, check_gap_step=ctx.retry == 0)
    except ValueError as exc:
        raise ModelRetry(f"{exc}. Return the complete output again, with every field.") from exc


INSUFFICIENT = TutorDiagnosis(
    steps=[Step(role="choose_method", status="missing")], confidence="low", evidence="insufficient"
)


async def diagnose(
    reasoning_input: ReasoningInput, model: Model, timeout: float = gateway.DEFAULT_TIMEOUT_SECONDS
) -> GatewayOk[TutorDiagnosis] | GatewayFallback[TutorDiagnosis]:
    """On failure the fallback says "insufficient evidence", so the turn asks a probe, never guesses."""
    return await gateway.call(
        reasoning_agent,
        reasoning_input.model_dump_json(indent=2),
        model=model,
        deps=reasoning_input,
        fallback=INSUFFICIENT,
        timeout=timeout,
    )
