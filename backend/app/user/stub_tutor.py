from app.seed.data import NIKOS_ID
from app.tutor.schema import (
    Alternative,
    ChooseStrategyResult,
    DimensionRating,
    EvidenceCounts,
    FollowUpDraft,
    Step,
    TutorFollowUpOutput,
    TutorTeachingOutput,
)
from app.user.ports import (
    FollowUpRequest,
    FollowUpResult,
    JudgeRequest,
    ProblemSetup,
    TeachRequest,
    TeachResult,
)
from app.session.schema import Solution
from app.tutor.schema import ReplyCheckView
from app.verification.schema import StudentCheckResult

# Hardcoded Maria and Nikos story (M1, docs/API_CONTRACT.md) so the frontend can integrate
# before the real agent exists. The real agent replaces this class; method reasons mirror the seed.

BALL_SOLUTION = Solution(
    result="20.4 m",
    steps=["At the highest point v = 0.", "Use v^2 = u^2 - 2gh.", "h = 400 / 19.6 = 20.4 m."],
)


class StubTutor:
    def __init__(self) -> None:
        self._variants = 0  # bumped on every regenerate, so a repeated follow-up becomes a new one

    async def set_up(self, problem: str, subject: str | None) -> ProblemSetup:
        return ProblemSetup(concept_name="Constant-acceleration kinematics", solution=BALL_SOLUTION)

    async def teach(self, request: TeachRequest) -> TeachResult:
        if request.student_id == NIKOS_ID:
            output = TutorTeachingOutput(
                steps=[
                    Step(role="choose_method", status="correct", quote="I used v^2 = u^2 - 2gh"),
                    Step(role="substitute", status="wrong", quote="I got h = -20.4 m"),
                ],
                dimensions=[DimensionRating(name="procedure", state="weak", evidence="Got a negative height.")],
                main_gap="procedure",
                alternatives=[Alternative(gap="concept", confidence="low")],
                confidence="medium",
                gap_repaired=request.teach_turns >= 2,
                reply=(
                    "Here is a similar problem solved step by step, with one sign left blank. "
                    "Which sign should go there, and why?"
                ),
            )
            method = ChooseStrategyResult(
                method="worked_example", mode="best_known",
                reason="Worked 5 of 6 times for you on procedure gaps.",
                evidence=EvidenceCounts(uses=6, independent_successes=5), last_success_days_ago=4,
            )
        else:
            output = TutorTeachingOutput(
                steps=[
                    Step(role="identify_quantities", status="correct", quote="initial velocity of 20 m/s"),
                    Step(role="choose_method", status="wrong", quote="I do not know how to get the height"),
                ],
                dimensions=[
                    DimensionRating(name="recognition", state="weak", evidence="Found the time, saw no way to the height."),
                    DimensionRating(name="procedure", state="strong", evidence="Time to the top computed correctly."),
                ],
                main_gap="recognition",
                alternatives=[Alternative(gap="representation", confidence="low")],
                confidence="medium",
                gap_repaired=request.teach_turns >= 2,
                reply=(
                    "Let's draw it. Sketch the ball going up and mark the point where its speed becomes 0. "
                    "What do you know at that point, and what do you want to find?"
                ),
            )
            method = ChooseStrategyResult(
                method="visual_decomposition", mode="best_known",
                reason="Worked 7 of 9 times for you on recognition gaps.",
                evidence=EvidenceCounts(uses=9, independent_successes=7), last_success_days_ago=6,
            )
        return TeachResult(
            output=output, method=method,
            reply_check=ReplyCheckView(approved=True, summary=f"No answer given. Method matches: {method.method}."),
        )

    async def follow_up(self, request: FollowUpRequest) -> FollowUpResult:
        if request.retry_reason:
            self._variants += 1
        if request.student_id == NIKOS_ID:
            u = 5 + self._variants
            draft = FollowUpDraft(
                problem=(
                    f"A ball is thrown downward at {u} m/s from a height of 30 m. How fast is it "
                    "moving when it reaches the ground? (Use g = 9.8 m/s^2)"
                ),
                concept_invariant="Constant-acceleration motion; keep the signs consistent.",
                target_gap="procedure", target_step="substitute", perturbation="context", difficulty="medium",
                hidden_rubric=[
                    "Takes downward as positive, so g and u have the same sign",
                    f"Substitutes u = {u}, a = 9.8, h = 30",
                    f"Reports about {(u * u + 2 * 9.8 * 30) ** 0.5:.1f} m/s",
                ],
            )
        else:
            u = 15 + self._variants
            draft = FollowUpDraft(
                problem=(
                    f"A stone is launched upward at {u} m/s from a balcony. How far above the "
                    "balcony does it rise before it stops? (Use g = 9.8 m/s^2)"
                ),
                concept_invariant="Constant-acceleration motion; choose the equation that needs no time.",
                target_gap="recognition", target_step="choose_method", perturbation="context", difficulty="medium",
                hidden_rubric=[
                    "Chooses v^2 = u^2 - 2gh without first finding the time",
                    f"Substitutes u = {u} and v = 0",
                    f"Reports about {u * u / (2 * 9.8):.1f} m",
                ],
            )
        return FollowUpResult(
            output=TutorFollowUpOutput(follow_up=draft),
            message="Now I am removing the support. New problem, same underlying idea, different surface.",
            reply_check=ReplyCheckView(
                approved=True,
                summary="Follow-up keeps the principle, changes the context, does not state the answer.",
            ),
        )

    async def judge(self, request: JudgeRequest) -> StudentCheckResult:
        return StudentCheckResult(
            mode="student_check", correct=True, reasoning_quality="strong", own_work=True,
            note="Chose the equation that needs no time and substituted correctly.",
        )
