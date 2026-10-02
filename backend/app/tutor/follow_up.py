"""The personal follow-up (F14) that is also the stress test (F15): one fresh problem, no support.

generate (LLM) -> code checks (not the original with new numbers, in the student's language)
  -> follow-up check (verifier LLM) -> approved, or regenerate with the reason (max 2) -> error
A follow-up is never faked: if none passes, the caller gets an error and the session says try again.
"""

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.ai_gateway import gateway
from app.common import trace
from app.common.vocab import GapType, RejectionReason, Strategy
from app.verification.agent import check_follow_up
from app.verification.schema import FollowUpCheckInput, FollowUpCheckResult

from .language import Language, written_in
from .schema import FollowUpDraft, Step, Text

INSTRUCTIONS = (Path(__file__).parent / "follow_up_prompt.txt").read_text(encoding="utf-8")
MAX_REGENERATIONS = 2
TOO_CLOSE = 0.6  # word overlap with the original above this is a paraphrase, not a new problem


class FollowUpInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem: Text
    concept_name: Text
    solution_steps: list[Text]
    main_gap: GapType | None = None
    gap_step: Step | None = None
    student_answers: list[str] = []
    method: Strategy | None = None
    language: Language = "English"
    retry_reason: RejectionReason | None = None
    retry_note: str | None = None


follow_up_agent = Agent(output_type=FollowUpDraft, instructions=INSTRUCTIONS, retries=1, name="tutor_follow_up")


class FollowUpUnavailable(RuntimeError):
    """No follow-up passed the checks; the session turns this into a retryable error."""


class Attempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: FollowUpDraft | None = None
    check: FollowUpCheckResult | None = None
    failure: str | None = None


def _words(text: str) -> set[str]:
    return set(re.findall(r"[^\W\d_]+", text.lower()))


def overlap(a: str, b: str) -> float:
    """Share of words two problems have in common (numbers ignored)."""
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa | wb else 1.0


async def write_follow_up(
    follow_up_input: FollowUpInput, model: Model, verifier_model: Model,
    timeout: float = gateway.DEFAULT_TIMEOUT_SECONDS,
) -> tuple[FollowUpDraft, FollowUpCheckResult, list[Attempt]]:
    attempts: list[Attempt] = []
    current = follow_up_input
    for number in range(1, 2 + MAX_REGENERATIONS):
        written = await gateway.call(follow_up_agent, current.model_dump_json(indent=2), model=model,
                                     fallback=None, timeout=timeout)
        if not written.ok or written.value is None:
            attempts.append(Attempt(failure=f"generation: {written.failure}: {written.detail}"))
            trace.record(trace.FollowUpResult, attempt=number, outcome="generation_failed",
                         failure=None if written.ok else written.failure, detail=None if written.ok else written.detail)
            break
        # Deterministic fact: the follow-up tests the gap that was taught (or transfer when none was).
        draft = FollowUpDraft.model_validate(
            {**written.value.model_dump(), "target_gap": follow_up_input.main_gap or "transfer"}
        )
        problem_reason = None
        if overlap(draft.problem, follow_up_input.problem) > TOO_CLOSE:
            problem_reason = ("invalid_followup", "This is the original problem with small changes. Write a new "
                              "situation that needs the same idea.")
        elif not written_in(draft.problem, follow_up_input.language):
            problem_reason = ("invalid_followup", f"Write the problem in {follow_up_input.language}.")
        if problem_reason:
            attempts.append(Attempt(draft=draft, failure=f"code: {problem_reason[1]}"))
            trace.record(trace.FollowUpResult, attempt=number, outcome="rejected_by_code", reason=problem_reason[0],
                         note=problem_reason[1], draft=draft)
            current = current.model_copy(update={"retry_reason": problem_reason[0], "retry_note": problem_reason[1]})
            continue
        checked = await check_follow_up(
            FollowUpCheckInput(
                original_problem=follow_up_input.problem, follow_up=draft.problem,
                concept_invariant=draft.concept_invariant, target_gap=draft.target_gap,
                target_step=draft.target_step, perturbation=draft.perturbation, hidden_rubric=draft.hidden_rubric,
            ),
            verifier_model, timeout,
        )
        if not checked.ok:
            attempts.append(Attempt(draft=draft, failure=f"verifier: {checked.failure}: {checked.detail}"))
            trace.record(trace.FollowUpResult, attempt=number, outcome="verifier_failed", failure=checked.failure,
                         detail=checked.detail, draft=draft)
            break
        attempts.append(Attempt(draft=draft, check=checked.value))
        trace.record(trace.FollowUpResult, attempt=number,
                     outcome="approved" if checked.value.approved else "rejected_by_verifier",
                     reason=checked.value.reason, note=checked.value.note, draft=draft)
        if checked.value.approved:
            return draft, checked.value, attempts
        current = current.model_copy(update={"retry_reason": checked.value.reason, "retry_note": checked.value.note})
    raise FollowUpUnavailable("; ".join(a.failure or (a.check.note if a.check else "") for a in attempts))
