"""The teaching step: one structured call that writes the reply from a finished diagnosis."""

from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.ai_gateway import gateway
from app.ai_gateway.schema import GatewayFallback, GatewayOk

from .language import FALLBACK_REPLY
from .schema import TeachingInput, TeachingReply

INSTRUCTIONS = (Path(__file__).parent / "teaching_prompt.txt").read_text(encoding="utf-8")

teaching_agent = Agent(
    output_type=TeachingReply,
    instructions=INSTRUCTIONS,
    retries=1,
    name="tutor_teaching",
)

async def write_reply(
    teaching_input: TeachingInput, model: Model, timeout: float = gateway.DEFAULT_TIMEOUT_SECONDS
) -> GatewayOk[TeachingReply] | GatewayFallback[TeachingReply]:
    return await gateway.call(
        teaching_agent,
        teaching_input.model_dump_json(indent=2),
        model=model,
        fallback=TeachingReply(reply=FALLBACK_REPLY[teaching_input.language]),
        timeout=timeout,
    )
