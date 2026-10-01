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

from .evidence import NOT_KNOWING, quote_found, substantive
from .repair import GAP_STEPS
from .schema import ReasoningDraft, ReasoningInput, Step, TutorDiagnosis

INSTRUCTIONS = (Path(__file__).parent / "reasoning_prompt.txt").read_text(encoding="utf-8")

reasoning_agent = Agent(
    output_type=ReasoningDraft,
    deps_type=ReasoningInput,
    instructions=INSTRUCTIONS,
    # One retry for the hard rules, plus one so an ask-once recheck never uses up the hard rules' retry.
    retries=2,
    # Diagnosis should be repeatable, not creative.
    model_settings={"temperature": 0},
    name="tutor_reasoning",
)


def apply_rules(
    diagnosis: ReasoningDraft | TutorDiagnosis, attempt: str, recheck: bool = True
) -> TutorDiagnosis:
    """Deterministic rules on top of the model's reading. They keep "not observed" apart from "missing".

    - No quote, no claim (rule 7): a correct or wrong step with no quote, or with a quote that cannot be
      found in the attempt, is not observed, so it is dropped. It is not turned into a missing step:
      that would invent a gap (for example a method the student clearly used but did not write out).
    - A "wrong" step whose quote only says the student does not know is missing.
    - Every step missing and nothing to go on (no gap found, or no quote beyond "I don't know"):
      there is no evidence to diagnose (insufficient, low, no gap). A missing step that carries
      the student's real reasoning is still evidence, so the model's gap is kept.
    - No gap found and no step wrong: the missing steps are steps the student did not narrate, not a
      gap, so they are dropped. A solution that really lacks a step keeps it, because the model names a gap.
    - A wrong step needs its error stated (what the student did, what it gives, what is asked), and an
      error belongs to a wrong step: when no step is wrong after these rules, there is no error to teach.

    Two consistency checks ask the model once to look again (recheck), and its second answer stands:
    - A step marked both wrong and missing: wrong must mean false in itself, not unfinished.
    - A concept gap is a wrong belief, so it shows as a wrong step; unfinished work alone is not one.
    - A gap must show at the step where that kind of gap lives.
    """
    observed = [
        Step(role=s.role, status=s.status, quote=s.quote)
        for s in diagnosis.steps
        if (s.status == "missing" and not s.quote) or (s.quote and quote_found(s.quote, attempt))
    ]
    steps = [
        s.model_copy(update={"status": "missing"}) if s.status == "wrong" and NOT_KNOWING.search(s.quote or "") else s
        for s in observed
    ]
    no_evidence = diagnosis.main_gap is None or not any(substantive(s.quote) for s in steps)
    update: dict = {"steps": steps}
    if not steps or (all(s.status == "missing" for s in steps) and no_evidence):
        update = {"steps": steps or [Step(role="choose_method", status="missing")], "evidence": "insufficient",
                  "confidence": "low", "main_gap": None, "alternatives": [], "error": None}
    elif diagnosis.evidence == "sufficient":
        if diagnosis.main_gap is None and not any(s.status == "wrong" for s in steps):
            update |= {"steps": [s for s in steps if s.status != "missing"], "alternatives": []}
        if all(s.status == "correct" for s in update["steps"]):
            update |= {"main_gap": None, "alternatives": [], "error": None}
    if diagnosis.error is None and any(s.status == "wrong" for s in update["steps"]):
        raise ValueError(
            "a step is marked wrong but error is empty. State the error at that step (student_did, "
            "actually_gives, asked_for, mismatch), or mark the step correct if the student's work there holds"
        )
    if not any(s.status == "wrong" for s in update["steps"]):
        update["error"] = None
    result = TutorDiagnosis.model_validate({**diagnosis.model_dump(), **{k: v for k, v in update.items()}})
    # Unfinished is not wrong. A step the model calls both wrong and not yet done is usually correct work
    # so far with the rest still to do; the model is asked to confirm the wrong label once.
    wrong = [s for s in result.steps if s.status == "wrong"]
    unfinished = [s for s in wrong if any(m.role == s.role and m.status == "missing" for m in result.steps)]
    if recheck and unfinished:
        role = unfinished[0].role
        raise ValueError(
            f"{role} is marked both wrong and missing. Wrong means what the student wrote at {role} is false in "
            "itself (a false value or claim, an invalid operation, or a result presented as something it is not). "
            f"If what they wrote at {role} is true so far and only unfinished, mark that part correct, keep the "
            "part still to do as missing, set error to null if no step is wrong, and choose the gap at the part "
            "they have not done. If it is false, keep it wrong"
        )
    if recheck and result.main_gap == "concept" and not wrong:
        raise ValueError(
            "main_gap is concept but no step is wrong. A concept gap is a wrong belief the student states or uses, "
            "so it shows as a wrong step. Mark the step where the wrong belief shows as wrong and state its error, "
            "or, if the student's work is true so far and only unfinished, choose the gap at the step they have "
            "not done"
        )
    # A gap must show where that kind of gap lives (for example a recognition gap at choose_method).
    roles = GAP_STEPS.get(result.main_gap, ()) if result.main_gap and recheck else ()
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
def follow_the_rules(ctx: RunContext[ReasoningInput], output: ReasoningDraft) -> ReasoningDraft:
    """A proposal the rules cannot turn into a valid diagnosis goes back to the model once."""
    try:
        # The consistency checks ask once; a second disagreement is accepted rather than
        # throwing the whole diagnosis away.
        apply_rules(output, ctx.deps.attempt, recheck=ctx.retry == 0)
    except ValueError as exc:
        raise ModelRetry(f"{exc}. Return the complete output again, with every field.") from exc
    return output


INSUFFICIENT = TutorDiagnosis(
    steps=[Step(role="choose_method", status="missing")], confidence="low", evidence="insufficient"
)


async def diagnose(
    reasoning_input: ReasoningInput, model: Model, timeout: float = gateway.DEFAULT_TIMEOUT_SECONDS
) -> GatewayOk[TutorDiagnosis] | GatewayFallback[TutorDiagnosis]:
    """The model proposes, code decides. On failure the fallback says "insufficient evidence",
    so the turn asks a probe, never guesses."""
    proposed = await gateway.call(
        reasoning_agent,
        reasoning_input.model_dump_json(indent=2),
        model=model,
        deps=reasoning_input,
        fallback=None,
        timeout=timeout,
    )
    if not proposed.ok or proposed.value is None:
        return GatewayFallback(value=INSUFFICIENT, failure=proposed.failure, detail=proposed.detail)
    # The validator already accepted this proposal, so the same rules turn it into the diagnosis.
    return GatewayOk(value=apply_rules(proposed.value, reasoning_input.attempt, recheck=False))
