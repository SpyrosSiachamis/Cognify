"""The reply checker: one structured call that approves or rejects a tutor reply.

Like the tutor, it has no model of its own; the caller passes one in (rule 4).
"""

import re
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.ai_gateway import gateway
from app.ai_gateway.schema import GatewayFallback, GatewayOk

from .schema import (
    FollowUpCheckInput,
    FollowUpCheckResult,
    ReplyCheckInput,
    ReplyCheckResult,
    StudentCheckInput,
    StudentCheckResult,
)

REPLY_INSTRUCTIONS = (Path(__file__).parent / "reply_prompt.txt").read_text(encoding="utf-8")
FOLLOW_UP_INSTRUCTIONS = (Path(__file__).parent / "followup_prompt.txt").read_text(encoding="utf-8")
STUDENT_INSTRUCTIONS = (Path(__file__).parent / "student_prompt.txt").read_text(encoding="utf-8")

reply_checker = Agent(
    output_type=ReplyCheckResult,
    instructions=REPLY_INSTRUCTIONS,
    retries=1,
    model_settings={"temperature": 0},
    name="reply_checker",
)


def leaked_answer(reply: str, final_answers: list[str]) -> str | None:
    """The cheap code check before the model check: a final answer string in the reply."""
    text = re.sub(r"\s+", " ", reply.lower())
    for answer in final_answers:
        needle = re.sub(r"\s+", " ", answer.lower()).strip()
        if needle and re.search(rf"(?<![\w.]){re.escape(needle)}(?![\w])", text):
            return answer
    return None


# Used only when the checker itself fails; the caller sees ok=False and never sends the reply.
UNCHECKED = ReplyCheckResult(
    mode="reply_check", approved=False, reason="heavy_hint", note="The reply could not be checked, so it is not sent."
)


async def check_reply(
    check_input: ReplyCheckInput,
    model: Model,
    final_answers: list[str] = [],
    timeout: float = gateway.DEFAULT_TIMEOUT_SECONDS,
) -> GatewayOk[ReplyCheckResult] | GatewayFallback[ReplyCheckResult]:
    """Code check first (no model call when it already catches a leak), then the model."""
    leak = leaked_answer(check_input.reply, final_answers)
    if leak:
        return GatewayOk(
            value=ReplyCheckResult(
                mode="reply_check",
                approved=False,
                reason="answer_leak",
                note=f"The reply contains the final answer ({leak}). Remove it and ask a question instead.",
            )
        )
    return await gateway.call(
        reply_checker, check_input.model_dump_json(indent=2), model=model, fallback=UNCHECKED, timeout=timeout
    )


follow_up_checker = Agent(
    output_type=FollowUpCheckResult,
    instructions=FOLLOW_UP_INSTRUCTIONS,
    retries=1,
    model_settings={"temperature": 0},
    name="follow_up_checker",
)

student_checker = Agent(
    output_type=StudentCheckResult,
    instructions=STUDENT_INSTRUCTIONS,
    retries=1,
    model_settings={"temperature": 0},
    name="student_checker",
)

UNCHECKED_FOLLOW_UP = FollowUpCheckResult(
    mode="follow_up_check", approved=False, reason="invalid_followup", note="The follow-up could not be checked."
)
UNJUDGED = StudentCheckResult(
    mode="student_check", correct=False, reasoning_quality="untested", own_work=False,
    note="The answer could not be judged.",
)


async def check_follow_up(
    check_input: FollowUpCheckInput, model: Model, timeout: float = gateway.DEFAULT_TIMEOUT_SECONDS
) -> GatewayOk[FollowUpCheckResult] | GatewayFallback[FollowUpCheckResult]:
    return await gateway.call(
        follow_up_checker, check_input.model_dump_json(indent=2), model=model, fallback=UNCHECKED_FOLLOW_UP,
        timeout=timeout,
    )


async def check_student(
    check_input: StudentCheckInput, model: Model, timeout: float = gateway.DEFAULT_TIMEOUT_SECONDS
) -> GatewayOk[StudentCheckResult] | GatewayFallback[StudentCheckResult]:
    """Evidence about the stress-test answer. A failure is never turned into a pass: the caller sees ok=False."""
    return await gateway.call(
        student_checker, check_input.model_dump_json(indent=2), model=model, fallback=UNJUDGED, timeout=timeout,
    )
