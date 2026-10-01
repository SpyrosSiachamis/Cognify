"""The tutor agent: one structured reasoning call per teaching turn.

The agent has no model of its own. The caller passes one in, so the provider,
timeouts and fallbacks stay in ai_gateway (CLAUDE.md rule 4).
"""

import re
from pathlib import Path

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from .schema import TutorInput, TutorTeachingOutput

INSTRUCTIONS = (Path(__file__).parent / "prompt.txt").read_text(encoding="utf-8")

tutor_agent = Agent(
    output_type=TutorTeachingOutput,
    deps_type=TutorInput,
    instructions=INSTRUCTIONS,
    retries=1,
    # Diagnosis should be repeatable, not creative.
    model_settings={"temperature": 0},
    name="tutor",
)


def _normalise(text: str) -> str:
    text = text.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip(" .,;:!?\"'")


@tutor_agent.output_validator
def quotes_come_from_the_attempt(
    ctx: RunContext[TutorInput], output: TutorTeachingOutput
) -> TutorTeachingOutput:
    """Every quote must be the student's own words from this attempt (rule 7).

    No quote, no claim: a step whose quote is not in the attempt becomes missing.
    Only if no quoted step is left does the model have to try again.
    """
    attempt = _normalise(ctx.deps.attempt)
    steps = [
        step if not step.quote or _normalise(step.quote) in attempt
        else step.model_copy(update={"status": "missing", "quote": None})
        for step in output.steps
    ]
    if not any(step.quote for step in steps):
        raise ModelRetry(
            "None of your quotes are in the student's attempt. Copy each quote exactly from the attempt, "
            "or mark the step missing with quote null. Return the complete output again, with every field."
        )
    return output.model_copy(update={"steps": steps})


async def run_tutor(tutor_input: TutorInput, model: Model) -> TutorTeachingOutput:
    """Diagnose the attempt and write one teaching reply. Raises if the model fails twice."""
    result = await tutor_agent.run(
        tutor_input.model_dump_json(indent=2), model=model, deps=tutor_input
    )
    return result.output
