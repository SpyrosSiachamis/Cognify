"""The reply checker: one structured call that approves or rejects a tutor reply.

Like the tutor, it has no model of its own; the caller passes one in (rule 4).
"""

import re
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.ai_gateway import gateway
from app.ai_gateway.schema import GatewayFallback, GatewayOk

from .schema import ReplyCheckInput, ReplyCheckResult

REPLY_INSTRUCTIONS = (Path(__file__).parent / "reply_prompt.txt").read_text(encoding="utf-8")

reply_checker = Agent(
    output_type=ReplyCheckResult,
    instructions=REPLY_INSTRUCTIONS,
    retries=1,
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
