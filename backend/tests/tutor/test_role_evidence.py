"""A step is observed only when its quote does that step's job.

From the live rectangle session (rectangle_factor_case.json: the problem, the student's last two answers, the tutor
message each answered and the diagnosis model's own proposals, as traced). Challenged on "(w + 8)(w - 6) = 0", the
student wrote "(w + 8)(w - 6) = w² + 2w - 48, so the factorization is correct." The model read the identity as a
correct set_up, then tagged "so the factorization is correct." as a WRONG interpret step. That clause says nothing
about what a result means for the rectangle: it states no value and names nothing the problem names, so there is no
interpretation in the answer to judge. It is not observed (dropped, like a quote that is not in the text), never wrong.
The case was not used to write the rule; the rule is the role's own definition (reasoning.ROLE_EVIDENCE).
"""

import asyncio
import json
from pathlib import Path

from app.session.schema import Solution
from app.tutor.agent import AgentTutor
from app.tutor.evidence import numeric_values, refers_to_problem
from app.tutor.reasoning import apply_rules
from app.tutor.schema import PriorDiagnosis, ReasoningDraft, Step

from .conftest import teach_request
from .fakes import FakeVerifier, ScriptedModel

CASE = json.loads((Path(__file__).parent / "rectangle_factor_case.json").read_text(encoding="utf-8"))
PROBLEM, (CHALLENGED, CHECKED) = CASE["problem"], CASE["turns"]
_, PROPOSAL = CASE["proposals"]
SOLUTION = Solution(result=CASE["solution_result"], steps=[
    "Let the width be w; the length is w + 2.", "w(w + 2) = 48, so w² + 2w - 48 = 0.",
    "(w + 8)(w - 6) = 0, so w = 6 or w = -8.", "A width cannot be negative, so w = 6 and the length is 8.",
])


def diagnose(proposal: dict, attempt: str = CHECKED):
    return apply_rules(ReasoningDraft.model_validate(proposal), attempt, recheck=False, has_tutor_message=True,
                       given=frozenset(numeric_values(PROBLEM)), problem=PROBLEM)


def test_a_remark_on_the_students_own_algebra_is_not_an_interpretation():
    d = diagnose(PROPOSAL)
    assert [(s.role, s.status) for s in d.steps] == [("set_up", "correct")]
    assert not any(s.role == "interpret" for s in d.steps)  # unobserved: neither wrong nor missing
    assert d.error is None and d.main_gap is None  # the error described the dropped step; nothing false is left


def test_the_turn_teaches_no_interpret_gap(store):
    prior = PriorDiagnosis(steps=[Step(role="set_up", status="wrong", quote="(w + 8)(w - 6) = 0")], main_gap="procedure")
    model = ScriptedModel([PROPOSAL])
    tutor = AgentTutor(store, model.model, FakeVerifier().model)
    result, trace = asyncio.run(tutor.teach_with_trace(teach_request(
        CHECKED, problem=PROBLEM, solution=SOLUTION, first_thought=False, tutor_message=CASE["tutor_messages"][1],
        prior=prior,
    )))
    shown = result.output
    assert not any(s.status == "wrong" for s in shown.steps)
    assert not any(s.role == "interpret" for s in shown.steps)
    assert trace.gap_step is None or trace.gap_step.role != "interpret"
    assert shown.main_gap != "representation"  # the gap the dropped step invented does not reach the student


def test_a_real_interpretation_that_is_false_stays_wrong():
    # Same shape, but the clause does interpret: it says which quantity a result is, for this problem.
    attempt = "(w + 8)(w - 6) = 0, so the width is -8 m."
    proposal = json.loads(json.dumps(PROPOSAL).replace("(w + 8)(w - 6) = w² + 2w - 48", "(w + 8)(w - 6) = 0")
                          .replace("so the factorization is correct.", "so the width is -8 m."))
    d = diagnose(proposal, attempt)
    assert ("interpret", "wrong") in [(s.role, s.status) for s in d.steps]
    assert d.error is not None


def test_refers_to_problem_reads_values_and_the_problems_own_words():
    assert refers_to_problem("so w = 6", PROBLEM)
    assert refers_to_problem("so the widths are positive", PROBLEM)  # another form of the problem's word
    assert not refers_to_problem("so the factorization is correct.", PROBLEM)
    assert not refers_to_problem("which means it works", PROBLEM)
    assert refers_to_problem("άρα το πλάτους είναι αρνητικό", "Ένα ορθογώνιο έχει πλάτος w.")  # Greek, inflected


def test_without_the_problem_text_no_role_is_checked():
    # Callers that do not pass the problem keep today's behaviour: only the quote's presence is checked.
    d = apply_rules(ReasoningDraft.model_validate(PROPOSAL), CHECKED, recheck=False, has_tutor_message=True)
    assert ("interpret", "wrong") in [(s.role, s.status) for s in d.steps]
