"""Cross-domain generalization: can the tutor tell what a student has shown from what is unfinished or wrong,
outside the seeded physics problem? The cases and their written expectations are in cross_domain_cases.py.

    docker compose exec backend python -m pytest -m live tests/tutor/test_cross_domain_live.py -q \
        --junitxml=/tmp/cross_domain.xml

Each case runs the real turn (set up, then teach) through the same entry point as test_general_live.py.
Every check is recorded, not only the first failing one: one JSON line per case is appended to the file
named by CROSS_DOMAIN_OUT (default /tmp/cross_domain.jsonl), with the actual diagnosis and the latency.
"""

import asyncio
import json
import os
import re
import time

import pytest

from app.tutor.agent import AgentTutor

from .conftest import teach_request
from .cross_domain_cases import CASES, CrossDomainCase

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("TUTOR_MODEL_ID"), reason="set TUTOR_MODEL_ID to a Bedrock model ID"),
]

OUT = os.environ.get("CROSS_DOMAIN_OUT", "/tmp/cross_domain.jsonl")


def squash(text: str | None) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def checks(case: CrossDomainCase, out, mode: str) -> dict[str, bool]:
    """The expected behaviour of the case's pattern, as separate yes/no checks."""
    steps = out.steps
    quoted = lambda status: any(s.status == status and squash(case.evidence) in squash(s.quote) for s in steps)
    if case.pattern == "incomplete":
        return {
            "credits_the_correct_work": quoted("correct"),
            "no_step_wrong": not any(s.status == "wrong" for s in steps),
            "no_error_stated": out.error is None,
            "something_still_missing": any(s.status == "missing" for s in steps),
            "gap_found_and_not_a_misconception": out.main_gap not in (None, "concept"),
            "teaches": mode == "teach",
        }
    return {  # incorrect, and right answer with wrong reasoning: the false claim itself is found
        "marks_the_false_claim_wrong": quoted("wrong"),
        "error_stated": out.error is not None,
        "gap_found": out.main_gap is not None,
        "teaches": mode == "teach",
    }


@pytest.mark.parametrize("case", CASES, ids=[c.case_id for c in CASES])
def test_cross_domain(store, case: CrossDomainCase):
    tutor = AgentTutor(store)
    started = time.monotonic()
    setup = asyncio.run(tutor.set_up(case.problem, None))
    result, trace = asyncio.run(tutor.teach_with_trace(teach_request(
        case.student, problem=case.problem, solution=setup.solution, concept_name=setup.concept_name)))
    latency = round(time.monotonic() - started, 1)
    out = result.output
    results = checks(case, out, trace.mode)
    record = {
        "case_id": case.case_id, "domain": case.domain, "pattern": case.pattern,
        "model_id": os.environ.get("TUTOR_MODEL_ID"), "passed": all(results.values()), "checks": results,
        "latency_seconds": latency, "latency_covers": "set_up and the full teaching turn",
        "actual": {
            "steps": [s.model_dump() for s in out.steps], "main_gap": out.main_gap, "evidence": out.evidence,
            "confidence": out.confidence, "error": out.error.model_dump() if out.error else None,
            "dimensions": [d.model_dump() for d in out.dimensions], "mode": trace.mode,
            "diagnosis_failure": trace.diagnosis_failure, "reply": out.reply,
            "reply_approved": result.reply_check.approved, "final_answer": setup.solution.result,
        },
    }
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(record, indent=2, ensure_ascii=False))
    failed = [name for name, ok in results.items() if not ok]
    assert not failed, f"failed checks: {', '.join(failed)}"
