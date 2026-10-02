"""Scripted stand-ins for the models, so the tutor pipeline can be tested offline.

One ScriptedModel answers both LLM steps: a request whose JSON has "mode" is the
teaching step, anything else is the reasoning step.
"""

import asyncio
import json

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

APPROVE = {"mode": "reply_check", "approved": True, "reason": None, "note": "Small question, no answer."}
SETUP = {"concept_name": "Constant-acceleration kinematics", "result": "20.4 m",
         "steps": ["At the highest point v = 0.", "Use v^2 = u^2 - 2gh.", "h = 400 / 19.6 = 20.4 m."]}
FOLLOW_UP = {
    "problem": "A stone is launched upward at 15 m/s from a balcony. How far above the balcony does it rise?",
    "concept_invariant": "Constant-acceleration motion; choose the relation that needs no time.",
    "target_gap": "recognition", "target_step": "choose_method", "perturbation": "context", "difficulty": "medium",
    "hidden_rubric": ["Uses v^2 = u^2 - 2gh with v = 0", "About 11.5 m"],
}
FOLLOW_UP_OK = {"mode": "follow_up_check", "approved": True, "reason": None, "note": "Same principle, new context."}
STUDENT_OK = {"mode": "student_check", "correct": True, "reasoning_quality": "strong", "own_work": True,
              "note": "Used the time-free relation on the new problem."}
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
    """Returns the scripted diagnoses and replies in order (the last one repeats).

    The set-up output is one dict for every call, or a list with one per call (the last repeats).
    """

    def __init__(self, diagnoses: list[dict], replies: list[str] = ["What do you know at the very top?"],
                 delay: float = 0, raise_on: str | None = None, setup: dict | list[dict] = SETUP,
                 follow_ups: list[dict] = [FOLLOW_UP]):
        self.diagnoses, self.replies, self.delay, self.raise_on = diagnoses, replies, delay, raise_on
        self.setup, self.follow_ups = setup, follow_ups
        self.setup_inputs: list[dict] = []
        self.follow_up_inputs: list[dict] = []
        self.reasoning_inputs: list[dict] = []
        self.teaching_inputs: list[dict] = []
        self.reasoning_calls = self.teaching_calls = 0
        self.model = FunctionModel(self.respond)

    async def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if self.delay:
            await asyncio.sleep(self.delay)
        sent = sent_json(messages)
        if "known_concepts" in sent:
            self.setup_inputs.append(sent)
            setups = self.setup if isinstance(self.setup, list) else [self.setup]
            output = setups[min(len(self.setup_inputs), len(setups)) - 1]
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])
        if "student_answers" in sent:
            self.follow_up_inputs.append(sent)
            output = self.follow_ups[min(len(self.follow_up_inputs), len(self.follow_ups)) - 1]
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])
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
    """Returns the given reply-check results in order and records what it was asked to check.

    Follow-up and student checks get their own scripted answers (approve, and a correct own-work answer).
    """

    def __init__(self, *results: dict, follow_up_checks: list[dict] = [FOLLOW_UP_OK],
                 student_checks: list[dict] = [STUDENT_OK]):
        self.results = results or (APPROVE,)
        self.follow_up_checks, self.student_checks = follow_up_checks, student_checks
        self.inputs: list[dict] = []
        self.follow_up_inputs: list[dict] = []
        self.student_inputs: list[dict] = []
        self.model = FunctionModel(self.respond)

    def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        sent = sent_json(messages)
        if "original_problem" in sent:
            self.follow_up_inputs.append(sent)
            out = self.follow_up_checks[min(len(self.follow_up_inputs), len(self.follow_up_checks)) - 1]
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])
        if "student_text" in sent:
            self.student_inputs.append(sent)
            out = self.student_checks[min(len(self.student_inputs), len(self.student_checks)) - 1]
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])
        self.inputs.append(sent)
        result = self.results[min(len(self.inputs), len(self.results)) - 1]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, result)])
