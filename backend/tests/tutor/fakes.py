"""Scripted stand-ins for the models, so the tutor pipeline can be tested offline.

One ScriptedModel answers both LLM steps: a request whose JSON has "mode" is the
teaching step, anything else is the reasoning step.
"""

import asyncio
import json

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

APPROVE = {"mode": "reply_check", "approved": True, "reason": None, "note": "Small question, no answer."}
HEAVY = {"mode": "reply_check", "approved": False, "reason": "heavy_hint", "note": "Two ideas at once; keep one."}


def sent_json(messages: list[ModelMessage]) -> dict:
    prompt = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
    return json.loads(prompt.content)


def diagnosis(*steps: tuple[str, str, str | None], gap: str | None = "recognition", confidence: str = "medium",
              evidence: str = "sufficient") -> dict:
    return {
        "steps": [{"role": r, "status": st, "quote": q} for r, st, q in steps],
        "dimensions": [],
        "main_gap": gap,
        "alternatives": [],
        "confidence": confidence,
        "evidence": evidence,
    }


class ScriptedModel:
    """Returns the scripted diagnoses and replies in order (the last one repeats)."""

    def __init__(self, diagnoses: list[dict], replies: list[str] = ["What do you know at the very top?"],
                 delay: float = 0, raise_on: str | None = None):
        self.diagnoses, self.replies, self.delay, self.raise_on = diagnoses, replies, delay, raise_on
        self.reasoning_inputs: list[dict] = []
        self.teaching_inputs: list[dict] = []
        self.reasoning_calls = self.teaching_calls = 0
        self.model = FunctionModel(self.respond)

    async def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if self.delay:
            await asyncio.sleep(self.delay)
        sent = sent_json(messages)
        if "mode" in sent:
            self.teaching_calls += 1
            if not self.teaching_inputs or self.teaching_inputs[-1] != sent:
                self.teaching_inputs.append(sent)
            output = {"reply": self.replies[min(len(self.teaching_inputs), len(self.replies)) - 1]}
        else:
            self.reasoning_calls += 1
            self.reasoning_inputs.append(sent)
            output = self.diagnoses[min(self.reasoning_calls, len(self.diagnoses)) - 1]
        if self.raise_on and self.raise_on in json.dumps(sent):
            raise RuntimeError("scripted provider failure")
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])


class FakeVerifier:
    """Returns the given check results in order and records what it was asked to check."""

    def __init__(self, *results: dict):
        self.results = results or (APPROVE,)
        self.inputs: list[dict] = []
        self.model = FunctionModel(self.respond)

    def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.inputs.append(sent_json(messages))
        result = self.results[min(len(self.inputs), len(self.results)) - 1]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, result)])
