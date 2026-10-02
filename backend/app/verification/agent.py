"""The reply checker: one structured call that approves or rejects a tutor reply.

Like the tutor, it has no model of its own; the caller passes one in (rule 4).
"""

import re
from pathlib import Path

from pydantic_ai import Agent, RunContext
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
    deps_type=ReplyCheckInput,
    retries=1,
    model_settings={"temperature": 0},
    name="reply_checker",
)

# A prompt line tagged "[if <condition>]" is sent only when that condition holds for this check, so a rule
# reaches the model only where it applies and every other check gets exactly the untagged prompt.
_CONDITIONAL_LINE = re.compile(r"^\[if (\w+)\]")


def reply_instructions(check_input: ReplyCheckInput) -> str:
    conditions = {
        "student_demonstrated": bool(check_input.student_demonstrated),
        "probe": check_input.main_gap is None,
    }
    lines = []
    for line in REPLY_INSTRUCTIONS.split("\n"):
        tag = _CONDITIONAL_LINE.match(line)
        if tag is None:
            lines.append(line)
        elif conditions[tag.group(1)]:
            lines.append(line[tag.end():])
    return "\n".join(lines)


@reply_checker.instructions
def _reply_instructions(ctx: RunContext[ReplyCheckInput]) -> str:
    return reply_instructions(ctx.deps)


def leaked_answer(reply: str, final_answers: list[str]) -> str | None:
    """The cheap code check before the model check: a final answer string in the reply."""
    text = re.sub(r"\s+", " ", reply.lower())
    for answer in final_answers:
        needle = re.sub(r"\s+", " ", answer.lower()).strip()
        if needle and re.search(rf"(?<![\w.]){re.escape(needle)}(?![\w])", text):
            return answer
    return None


# A real operation: an operator between two numbers (a unit may follow the first, as in "120 km / 2 h"), so the
# slash in "m/s" or a minus sign alone is not one.
_OPERATION = re.compile(
    r"\d\s*(?:[^\W\d]+\s*)?(?:[+\-*/×÷^]|\b(?:plus|minus|times|over|divided by|multiplied by)\b)\s*[(\d]", re.I
)
# Where a result is stated: "=" or a result word. The text after the LAST one is the result.
_RESULT_MARK = re.compile(r"=|\b(?:is|equals|gives|makes|leaves)\b", re.I)
_LEADING_NUMBER = re.compile(r"\s*(-?\d+(?:[.,]\d+)?)")


def _core(answer: str) -> str | None:
    """The answer's single number: "4 books" -> "4", "x = 4" -> "4". A compound answer ("6 m × 8 m") has none,
    so deriving one part of it never unlocks the whole answer."""
    match = re.fullmatch(r"\s*(?:[^\W\d]\w*\s*=\s*)?(-?\d+(?:[.,]\d+)?)\s*([^\W\d][\w/^²³]*\.?)?\s*", answer)
    return match.group(1).replace(",", ".") if match else None


def _unit(answer: str) -> str | None:
    """The unit word after the answer's number, if any ("4 books" -> "books")."""
    match = re.fullmatch(r"\s*(?:[^\W\d]\w*\s*=\s*)?-?\d+(?:[.,]\d+)?\s*([^\W\d][\w/^²³]*)\.?\s*", answer)
    return match.group(1).lower() if match else None


def _has_value(text: str, value: str) -> bool:
    """The exact value on its own: "4" is not in "24", "2" is not in "2.04" (strict on both sides)."""
    canon = text.replace(",", ".").lower()
    return re.search(rf"(?<![\w.]){re.escape(value)}(?!\w|\.\d)", canon) is not None


def _calculated_result(quote: str) -> str | None:
    """The number the student's own calculation produced: the first number after the last result marker, when the
    text before it holds a real operation. None for a guess, a bare value or a restated quantity."""
    marks = list(_RESULT_MARK.finditer(quote))
    if not marks:
        return None
    before, after = quote[: marks[-1].start()], quote[marks[-1].end():]
    number = _LEADING_NUMBER.match(after)
    if not number or not _OPERATION.search(before):
        return None
    return number.group(1).replace(",", ".")


def demonstrated_answers(
    steps: list[tuple[str, str, str | None]], final_answers: list[str], problem: str
) -> tuple[list[str], list[str]]:
    """What the student has derived themselves, as (quotes, answer variants to leave out of the leak search).

    steps are (role, status, quote) from attempts with no wrong step. An answer counts as demonstrated only when a
    correct compute or interpret quote shows it as the result of the student's own calculation (see
    _calculated_result), and it is not a quantity given in the problem. A variant with a unit ("4 books") is left
    out only if the student's own demonstrated work names that unit: deriving "24 ÷ 6 = 4" shows the 4, not what it
    counts. A guess ("is it 4?") or an unworked value is never demonstrated, so a reply stating it is still a leak.
    """
    cores = {c for c in (_core(a) for a in final_answers) if c and not _has_value(problem, c)}
    quotes, shown = [], set()
    for role, status, quote in steps:
        # The operation-and-result test is the gate: compact work like "24/6 = 4" counts, a bare value never does.
        if status != "correct" or role not in ("compute", "interpret") or not quote:
            continue
        result = _calculated_result(quote)
        if result in cores:
            shown.add(result)
            quotes.append(quote)
    said = " ".join(quotes).lower()

    def unlocked(answer: str) -> bool:
        if _core(answer) not in shown:
            return False
        unit = _unit(answer)
        return unit is None or re.search(rf"\b{re.escape(unit)}\b", said) is not None

    return quotes, [a for a in final_answers if unlocked(a)]


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
    # An empty student_demonstrated is left out, like its prompt lines.
    payload = check_input.model_dump_json(indent=2, exclude={"student_demonstrated"} if not check_input.student_demonstrated else None)
    return await gateway.call(
        reply_checker, payload, model=model, deps=check_input, fallback=UNCHECKED, timeout=timeout
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
