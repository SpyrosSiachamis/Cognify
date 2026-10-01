"""Cross-domain evaluation v2: 70 cases, 7 domains x 10 reasoning patterns. The cases and their expectations are
in cross_domain_cases_v2.py; the offline validation is test_cross_domain_v2_cases.py.

    docker compose exec -e CROSS_DOMAIN_V2_OUT=/tmp/cross_domain_v2.jsonl backend python -m pytest -m live \
        tests/tutor/test_cross_domain_v2_live.py -q --junitxml=/tmp/cross_domain_v2.xml

Same entry point as v1 (set_up, then teach_with_trace). Every check is recorded, not only the first failing one:
one JSON line per case with the actual diagnosis, the turn's trace and the latency.
"""

import asyncio
import datetime
import json
import os
import re
import time

import pytest

from app.tutor.agent import AgentTutor
from app.user.ports import ProblemSetup, TeachRequest

from .conftest import teach_request
from .cross_domain_cases_v2 import CASES, CrossDomainCaseV2

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("TUTOR_MODEL_ID"), reason="set TUTOR_MODEL_ID to a Bedrock model ID"),
]

OUT = os.environ.get("CROSS_DOMAIN_V2_OUT", "/tmp/cross_domain_v2.jsonl")

# Which checks are about the diagnosis (comparable to v1) and which about the tutoring reply.
DIAGNOSIS_CHECKS = {
    "credits_valid_work", "marks_the_error_wrong", "no_step_wrong", "error_stated", "no_error_stated", "gap_found",
    "no_gap", "gap_is_concept", "gap_not_concept", "something_missing", "nothing_missing", "mode_as_expected",
    "repair_state",
}
TUTORING_CHECKS = {"no_answer_leak", "reply_approved"}


def squash(text: str | None) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def build_request(case: CrossDomainCaseV2, setup: ProblemSetup) -> TeachRequest:
    """What the tutor receives: the problem and the student's text (and, for a follow-up, the previous turn's
    diagnosis exactly as the session passes it). No expectation field is used."""
    update = dict(problem=case.problem, solution=setup.solution, concept_name=setup.concept_name)
    if case.prior is not None:
        update |= dict(prior=case.prior, first_thought=False, hints_used=1, teach_turns=2)
    return teach_request(case.student, **update)


def checks(case: CrossDomainCaseV2, out, mode: str, repaired: bool, approved: bool) -> dict[str, bool]:
    """The case's expectations as separate yes/no checks. Only the expected behaviours are checked."""
    e, steps = case.expect, out.steps
    quoted = lambda status, text: any(s.status == status and squash(text) in squash(s.quote) for s in steps)
    result: dict[str, bool] = {}
    if e.credit_required:
        result["credits_valid_work"] = quoted("correct", case.credit_quote)
    if e.wrong_required:
        result["marks_the_error_wrong"] = quoted("wrong", case.error_quote)
    if e.no_wrong:
        result["no_step_wrong"] = not any(s.status == "wrong" for s in steps)
    if e.error_required:
        result["error_stated"] = out.error is not None
    if e.no_error:
        result["no_error_stated"] = out.error is None
    if e.gap_required:
        result["gap_found"] = out.main_gap is not None
    if e.no_gap:
        result["no_gap"] = out.main_gap is None
    if e.gap_concept is True:
        result["gap_is_concept"] = out.main_gap == "concept"
    if e.gap_concept is False:
        result["gap_not_concept"] = out.main_gap is not None and out.main_gap != "concept"
    if e.missing_required:
        result["something_missing"] = any(s.status == "missing" for s in steps)
    if e.no_missing:
        result["nothing_missing"] = not any(s.status == "missing" for s in steps)
    result["mode_as_expected"] = mode in e.modes
    if e.repaired is not None:
        result["repair_state"] = repaired == e.repaired
    if case.leak_forms and mode in ("teach", "probe"):
        result["no_answer_leak"] = not any(squash(form) in squash(out.reply) for form in case.leak_forms)
    if e.reply_approved:
        result["reply_approved"] = approved
    return result


@pytest.mark.parametrize("case", CASES, ids=[c.case_id for c in CASES])
def test_cross_domain_v2(store, case: CrossDomainCaseV2):
    tutor = AgentTutor(store)
    stamp = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    started = time.monotonic()
    setup = asyncio.run(tutor.set_up(case.problem, None))
    result, trace = asyncio.run(tutor.teach_with_trace(build_request(case, setup)))
    latency = round(time.monotonic() - started, 1)
    out = result.output
    results = checks(case, out, trace.mode, out.gap_repaired, result.reply_check.approved)
    record = {
        "case_id": case.case_id, "domain": case.domain, "pattern": case.pattern, "repair": case.repair,
        "model_id": os.environ.get("TUTOR_MODEL_ID"), "timestamp": stamp,
        "passed": all(results.values()), "checks": results,
        "latency_seconds": latency, "latency_covers": "set_up and the full teaching turn",
        "actual": {
            "steps": [s.model_dump() for s in out.steps], "main_gap": out.main_gap,
            "alternatives": [a.model_dump() for a in out.alternatives], "evidence": out.evidence,
            "confidence": out.confidence, "error": out.error.model_dump() if out.error else None,
            "dimensions": [d.model_dump() for d in out.dimensions], "mode": trace.mode,
            "diagnosis_failure": trace.diagnosis_failure, "gap_repaired": out.gap_repaired,
            "repair_reason": trace.repair_reason, "strategy": trace.strategy.model_dump() if trace.strategy else None,
            "drafts": [{"reply": d.reply, "approved": d.check.approved if d.check else None,
                        "reason": d.check.reason if d.check else None, "note": d.check.note if d.check else None,
                        "failure": d.failure} for d in trace.drafts],
            "fallback": trace.fallback, "reply": out.reply, "reply_approved": result.reply_check.approved,
            "final_answer": setup.solution.result,
        },
    }
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(record, indent=2, ensure_ascii=False))
    failed = [name for name, ok in results.items() if not ok]
    assert not failed, f"failed checks: {', '.join(failed)}"
