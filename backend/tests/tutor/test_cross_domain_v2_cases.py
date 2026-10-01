"""Offline validation of the cross-domain v2 cases (no model calls): structure, consistency, quotes, no leakage of
expectations into what the tutor sees, and that the runner sends only the intended inputs."""

import asyncio
import re
from collections import Counter

import pytest

from app.tutor.agent import AgentTutor
from app.user.ports import ProblemSetup
from app.session.schema import Solution

from .cross_domain_cases_v2 import CASES, DOMAINS, PATTERNS, CrossDomainCaseV2
from .fakes import FakeVerifier, ScriptedModel, diagnosis
from .test_cross_domain_v2_live import build_request, squash

EXPECTATION_FIELDS = ("demonstrated", "missing", "error", "expected_diagnosis", "rationale", "trap_description")
BANNED = ("misconception", "incomplete", "trap", "lucky guess", "rationale", "diagnosis", "pattern",
          "repair", "evidence localization")
FAKE_SETUP = ProblemSetup(concept_name="Test concept", solution=Solution(result="R", steps=["S"]))


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def shared_run(a: str, b: str, n: int = 6) -> str | None:
    """A run of n consecutive words that appears in both texts, if any."""
    grams = {tuple(words(a)[i:i + n]) for i in range(len(words(a)) - n + 1)}
    wb = words(b)
    return next((" ".join(g) for i in range(len(wb) - n + 1) if (g := tuple(wb[i:i + n])) in grams), None)


def by_id(case: CrossDomainCaseV2) -> str:
    return case.case_id


def test_seventy_cases_ten_per_domain_one_per_pattern():
    assert len(CASES) == 70
    assert len({c.case_id for c in CASES}) == 70, "case_ids must be unique"
    assert Counter(c.domain for c in CASES) == {d: 10 for d in DOMAINS}
    for domain in DOMAINS:
        assert sorted(c.pattern for c in CASES if c.domain == domain) == sorted(PATTERNS), domain


def test_traps_are_all_covered():
    covered = Counter(t for c in CASES for t in c.traps)
    assert set(covered) == set("ABCDEFGHIJ"), f"missing traps: {set('ABCDEFGHIJ') - set(covered)}"
    assert all(covered[t] >= 2 for t in "ABCDEFGHIJ"), covered


@pytest.mark.parametrize("case", CASES, ids=by_id)
def test_required_fields_are_present(case: CrossDomainCaseV2):
    for name in ("problem", "student", "demonstrated", "missing", "expected_diagnosis", "rationale",
                 "trap_description"):
        assert getattr(case, name).strip(), f"{name} is empty"
    assert case.domain in DOMAINS and case.pattern in PATTERNS
    assert set(case.traps) <= set("ABCDEFGHIJ")


@pytest.mark.parametrize("case", CASES, ids=by_id)
def test_quotes_needed_by_the_expectations_exist_in_the_student_text(case: CrossDomainCaseV2):
    e = case.expect
    assert (case.credit_quote is not None) == e.credit_required, "credit_quote must exist exactly when credit is required"
    assert (case.error_quote is not None) == e.wrong_required, "error_quote must exist exactly when a wrong step is required"
    for quote in (case.credit_quote, case.error_quote):
        if quote is not None:
            assert squash(quote) in squash(case.student), f"quote not in the student's text: {quote!r}"
    if case.credit_quote and case.error_quote:
        assert squash(case.credit_quote) not in squash(case.error_quote), "credit and error quotes must differ"


@pytest.mark.parametrize("case", CASES, ids=by_id)
def test_pattern_expectations_are_consistent(case: CrossDomainCaseV2):
    e = case.expect
    assert not (e.no_wrong and e.wrong_required) and not (e.no_error and e.error_required)
    assert not (e.no_gap and (e.gap_required or e.gap_concept is not None))
    assert not (e.no_missing and e.missing_required)
    if case.pattern == "repair_followup":
        assert case.repair in ("genuine", "partial", "false") and case.prior is not None and case.previous_attempt
        assert ("G" in case.traps) == (case.repair == "partial") and ("H" in case.traps) == (case.repair == "false")
    else:
        assert case.repair is None and case.prior is None and case.previous_attempt is None
    if case.pattern == "no_reasoning":
        assert len(words(case.student)) <= 2, "a no-reasoning case is a bare answer"


@pytest.mark.parametrize("case", [c for c in CASES if c.prior is not None], ids=by_id)
def test_prior_quotes_come_from_the_previous_attempt(case: CrossDomainCaseV2):
    for step in case.prior.steps:
        if step.quote:
            assert squash(step.quote) in squash(case.previous_attempt), step.quote


@pytest.mark.parametrize("case", CASES, ids=by_id)
def test_expectations_do_not_leak_into_the_inputs(case: CrossDomainCaseV2):
    inputs = f"{case.problem}\n{case.student}".lower()
    for word in BANNED:
        assert word not in inputs, f"expectation wording {word!r} in the input"
    for name in EXPECTATION_FIELDS:
        text = getattr(case, name) or ""
        run = shared_run(text, inputs)
        assert run is None, f"{name} shares the words {run!r} with the input"
    for form in case.leak_forms:
        assert squash(form) not in squash(case.problem) and squash(form) not in squash(case.student), form


@pytest.mark.parametrize("case", CASES, ids=by_id)
def test_the_request_carries_only_the_intended_inputs(case: CrossDomainCaseV2):
    request = build_request(case, FAKE_SETUP)
    assert request.problem == case.problem and request.student_text == case.student
    assert (request.prior == case.prior) and (request.first_thought == (case.prior is None))
    sent = request.model_dump_json()
    for name in EXPECTATION_FIELDS:
        text = getattr(case, name)
        if text and len(text) > 12:
            assert text not in sent, f"{name} reaches the tutor"
    if case.previous_attempt:
        assert case.previous_attempt not in sent, "the previous attempt itself is not sent, only its diagnosis"


@pytest.mark.parametrize("case", CASES[::7], ids=by_id)
def test_the_reasoning_step_sees_only_problem_attempt_and_answer(store, case: CrossDomainCaseV2):
    model = ScriptedModel([diagnosis(("choose_method", "missing", None), gap=None, evidence="insufficient",
                                     confidence="low")])
    tutor = AgentTutor(store, model.model, FakeVerifier().model)
    asyncio.run(tutor.teach_with_trace(build_request(case, FAKE_SETUP)))
    sent = model.reasoning_inputs[0]
    assert set(sent) == {"problem", "attempt", "final_answer"}
    assert (sent["problem"], sent["attempt"], sent["final_answer"]) == (case.problem, case.student, "R")
