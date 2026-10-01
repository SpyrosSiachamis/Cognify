"""Master session shapes (docs/API_CONTRACT.md, Part A): start, attempt, verdict and exit.

The hidden solution, hidden rubric and verifier notes have no field in any
response model, so they cannot leave the backend. The only solution field is the
one returned by an explicit exit.
"""

from typing import Annotated

from pydantic import UUID4, BaseModel, ConfigDict, Field, model_validator

from app.common.contract import CONCEPT, MARIA, PROBLEM, SESSION, contract
from app.common.vocab import GapType, Phase, State, Strategy, VerdictResult
from app.tutor.schema import EvidenceCounts, TutorTurn

Text = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- POST /api/session (start Master) ----


class SessionStartRequest(StrictModel):
    model_config = contract(
        {"problem": PROBLEM, "subject": "physics", "student_id": MARIA, "force_experiment": False}
    )

    problem: str = Field(min_length=1, max_length=2000)
    subject: str | None = None
    student_id: UUID4
    force_experiment: bool = False


class SessionStartResponse(StrictModel):
    model_config = contract(
        {
            "session_id": SESSION,
            "phase": "ask_first_thought",
            "message": "Before I help, what would you try first? Even an incomplete idea is useful.",
            "hints_used": 0,
        }
    )

    session_id: UUID4
    phase: Phase
    message: Text
    hints_used: int = Field(ge=0)


# ---- POST /api/session/{id}/attempt ----


class StudentAttempt(StrictModel):
    """The same shape on every turn."""

    model_config = contract({"text": "I found the time to the top, but not the height."})

    text: Text


class ConceptChange(StrictModel):
    concept_id: UUID4
    name: Text
    before: State
    after: State


class StrategyChange(StrictModel):
    gap: GapType
    method: Strategy
    before: EvidenceCounts
    after: EvidenceCounts


class VerdictChanges(StrictModel):
    concept: ConceptChange
    strategy: StrategyChange | None = None  # None when no teaching method was used in the session


class Verdict(StrictModel):
    result: VerdictResult
    evidence: Text
    independent: bool
    remaining_gap: GapType | None = None
    changes: VerdictChanges

    @model_validator(mode="after")
    def verified_needs_independence(self) -> "Verdict":
        if self.result == "VERIFIED" and not self.independent:
            raise ValueError("VERIFIED requires independent=True (a lucky answer is NOT YET)")
        return self


class VerdictTurn(StrictModel):
    """The end of the stress test. VERIFIED is decided by code, not by the model."""

    model_config = contract(
        {
            "session_id": SESSION,
            "phase": "verdict",
            "session_over": True,
            "verdict": {
                "result": "VERIFIED",
                "evidence": "Chose the equation that needs no time, with no hints on this problem.",
                "independent": True,
                "remaining_gap": None,
                "changes": {
                    "concept": {"concept_id": CONCEPT, "name": "Constant-acceleration kinematics", "before": "fragile", "after": "verified"},
                    "strategy": {
                        "gap": "recognition",
                        "method": "visual_decomposition",
                        "before": {"uses": 9, "independent_successes": 7},
                        "after": {"uses": 10, "independent_successes": 8},
                    },
                },
            },
        }
    )

    session_id: UUID4
    phase: Phase
    session_over: bool
    message: str | None = None
    verdict: Verdict

    @model_validator(mode="after")
    def verdict_phase_and_ending(self) -> "VerdictTurn":
        if self.phase != "verdict":
            raise ValueError("a verdict turn has phase verdict")
        if self.verdict.result == "VERIFIED" and not self.session_over:
            raise ValueError("a VERIFIED verdict ends the session")
        return self


# What POST /api/session/{id}/attempt returns.
AttemptResponse = TutorTurn | VerdictTurn


# ---- POST /api/session/{id}/exit ----


class Solution(StrictModel):
    result: Text
    steps: list[Text] = Field(min_length=1)


class ExitResponse(StrictModel):
    """Explicit exit: the solution is returned and no evidence is recorded."""

    model_config = contract(
        {
            "phase": "exited",
            "solution": {"result": "20.4 m", "steps": ["At the highest point v = 0.", "h = 400 / 19.6 = 20.4 m."]},
            "evidence_recorded": False,
        }
    )

    phase: Phase
    solution: Solution
    evidence_recorded: bool = False

    @model_validator(mode="after")
    def exited_without_evidence(self) -> "ExitResponse":
        if self.phase != "exited":
            raise ValueError("an exit response has phase exited")
        if self.evidence_recorded:
            raise ValueError("exit records no evidence")
        return self
