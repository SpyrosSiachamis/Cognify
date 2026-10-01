"""Build docs/cross_domain_evaluation_v2.json and docs/CROSS_DOMAIN_EVALUATION_V2.md from the raw run files.

    python3 backend/scripts/cross_domain_v2_report.py --results run.jsonl --junit run.xml --conditions cond.json

Run on the host from the repo root. It reads only the raw records, the case definitions and the v1 results; it
never calls a model. Every rate keeps its numerator, denominator, check set and case count.
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from tests.tutor.cross_domain_cases_v2 import CASES, DOMAINS, PATTERNS, CrossDomainCaseV2  # noqa: E402

DIAGNOSIS_CHECKS = {
    "credits_valid_work", "marks_the_error_wrong", "no_step_wrong", "error_stated", "no_error_stated", "gap_found",
    "no_gap", "gap_is_concept", "gap_not_concept", "something_missing", "nothing_missing", "mode_as_expected",
    "repair_state",
}
CHECK_MEANING = {
    "credits_valid_work": "a step marked correct quotes the valid work (credit_quote)",
    "marks_the_error_wrong": "a step marked wrong quotes the false or slipped claim (error_quote)",
    "no_step_wrong": "no step is marked wrong",
    "error_stated": "an error analysis is stated",
    "no_error_stated": "no error analysis is stated",
    "gap_found": "a main gap is named",
    "no_gap": "no main gap is named",
    "gap_is_concept": "the main gap is concept",
    "gap_not_concept": "a main gap is named and it is not concept",
    "something_missing": "some step is marked missing",
    "nothing_missing": "no step is marked missing",
    "mode_as_expected": "the turn's mode is one of the allowed modes",
    "repair_state": "the code repair check gives the expected result",
    "no_answer_leak": "the reply contains none of the case's answer strings",
    "reply_approved": "the verifier approved a teaching draft (no safe fallback reply)",
}
FALSE_CLAIM_PATTERNS = {"incorrect_conceptual", "incorrect_local_error", "correct_answer_wrong_reasoning",
                        "correct_reasoning_wrong_answer", "misconception"}
INCOMPLETE = {"incomplete_early_stop", "incomplete_implicit_step"}
# v1's exact criteria, to compare like with like on the three v1 patterns.
V1_CRITERIA = {
    "incomplete_early_stop": {"credits_valid_work", "no_step_wrong", "no_error_stated", "something_missing",
                              "gap_not_concept", "mode_as_expected"},
    "incorrect_conceptual": {"marks_the_error_wrong", "error_stated", "gap_found", "mode_as_expected"},
    "correct_answer_wrong_reasoning": {"marks_the_error_wrong", "error_stated", "gap_found", "mode_as_expected"},
}
# Diagnosis-level causes first (a failed diagnosis call explains everything after it), then the teaching turn.
CATEGORY_ORDER = ["Infrastructure/API", "Timeout", "Structured output", "Diagnosis", "Step segmentation",
                  "Evidence grounding"]
LATE_ORDER = ["Answer leakage", "Structured output (teaching step)", "Timeout (teaching step)", "Teaching method",
              "Verification", "Other"]


def squash(text: str | None) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def classify(case: CrossDomainCaseV2, record: dict | None, junit_error: str) -> tuple[str | None, list[str], list[str], str]:
    """(primary category, all categories, diagnosis sub-types, notes) for a failed case."""
    if record is None:
        cat = "Infrastructure/API" if junit_error else "Other"
        return cat, [cat], [], "no record was written; " + (junit_error[:300] or "no junit detail")
    if record["passed"]:
        return None, [], [], ""
    a, failed = record["actual"], [k for k, ok in record["checks"].items() if not ok]
    cats, late, subs, notes = set(), set(), [], []
    failure = a.get("diagnosis_failure") or ""
    if failure.startswith("timeout"):
        cats.add("Timeout")
    elif failure.startswith("invalid_output"):
        cats.add("Structured output")
    elif failure.startswith("provider_error"):
        cats.add("Infrastructure/API")
    if failure:
        notes.append(f"diagnosis_failure: {failure}")
    steps = a["steps"]
    in_steps = lambda text, pred: [s for s in steps if pred(s) and squash(text) in squash(s["quote"])]
    for check in failed:
        if check == "credits_valid_work":
            merged = in_steps(case.credit_quote, lambda s: s["status"] != "correct")
            if merged and any(len(squash(s["quote"])) > len(squash(case.credit_quote)) + 10 for s in merged):
                cats.add("Step segmentation")
                notes.append(f"the valid work sits inside a {merged[0]['status']} step quoting more text")
                subs.append("failure to credit valid work")
            elif merged:
                cats.add("Diagnosis"); subs.append("failure to credit valid work")
                if merged[0]["status"] == "wrong":
                    subs.append("false positive error")
            elif any(s["status"] == "correct" for s in steps):
                cats.add("Evidence grounding")
                notes.append("a correct step exists but none quotes the valid work")
            else:
                cats.add("Diagnosis"); subs.append("failure to credit valid work")
        elif check == "marks_the_error_wrong":
            if in_steps(case.error_quote, lambda s: s["status"] in ("correct", "missing")):
                cats.add("Diagnosis"); subs.append("missed error")
            elif any(s["status"] == "wrong" for s in steps):
                cats.add("Evidence grounding")
                notes.append("a wrong step exists but none quotes the expected claim")
            else:
                cats.add("Diagnosis"); subs.append("missed error")
        elif check in ("no_step_wrong", "no_error_stated"):
            cats.add("Diagnosis"); subs.append("false positive error")
        elif check == "error_stated":
            cats.add("Diagnosis"); subs.append("missed error")
        elif check in ("gap_found", "something_missing"):
            cats.add("Diagnosis")
            subs.append("missed incomplete state" if case.pattern in INCOMPLETE else "missed error")
        elif check in ("no_gap", "nothing_missing"):
            cats.add("Diagnosis"); subs.append("invented gap")
        elif check == "gap_is_concept":
            cats.add("Diagnosis"); subs.append("missed misconception")
        elif check == "gap_not_concept":
            cats.add("Diagnosis")
            if a["main_gap"] == "concept":
                subs.append("false misconception")
            else:
                subs.append("missed incomplete state" if case.pattern in INCOMPLETE else "missed error")
        elif check == "mode_as_expected":
            cats.add("Diagnosis")
            if case.pattern == "correct_work":
                subs.append("invented gap")
            elif case.pattern in INCOMPLETE:
                subs.append("missed incomplete state")
            elif case.pattern == "repair_followup":
                subs.append("incorrect repair state")
            elif case.pattern == "no_reasoning":
                subs.append("invented gap")
            else:
                subs.append("missed error")
            notes.append(f"mode was {a['mode']}, allowed {sorted(case.expect.modes)}")
        elif check == "repair_state":
            cats.add("Diagnosis"); subs.append("incorrect repair state")
            notes.append(f"repair check: {a['repair_reason']}")
        elif check == "no_answer_leak":
            late.add("Answer leakage")
        elif check == "reply_approved":
            reasons = Counter(d["reason"] for d in a["drafts"] if d["reason"])
            draft_failures = [d["failure"] for d in a["drafts"] if d["failure"]]
            # Teaching-step failures rank after the diagnosis: they do not explain a diagnosis error.
            for failure_text in draft_failures:
                late.add("Structured output (teaching step)" if "invalid_output" in failure_text else
                         "Timeout (teaching step)" if "timeout" in failure_text else "Other")
            if reasons.keys() & {"method_drift", "off_target"}:
                late.add("Teaching method")
            if reasons.keys() & {"answer_leak", "heavy_hint"}:
                late.add("Verification")
            if not reasons and not draft_failures:
                late.add("Other")
            notes.append(f"verifier rejections: {dict(reasons)}" + (f"; draft failures: {draft_failures}" if draft_failures else ""))
    ordered = [c for c in CATEGORY_ORDER if c in cats] + [c for c in LATE_ORDER if c in late]
    ordered = ordered or ["Assertion/test expectation"]
    if len(ordered) > 1:
        notes.append("several categories apply; primary chosen by the fixed order "
                     + " > ".join(CATEGORY_ORDER + LATE_ORDER))
    return ordered[0], ordered, sorted(set(subs)), "; ".join(notes)


def rate(passed: int, total: int) -> dict:
    return {"passed": passed, "total": total, "failed": total - passed,
            "pass_rate_percent": round(100 * passed / total, 1) if total else None,
            "display": f"{passed} / {total} = {100 * passed / total:.1f}%" if total else "0 / 0"}


def case_rows(results: list[dict], key: str, values) -> list[dict]:
    out = []
    for v in values:
        sel = [r for r in results if r[key] == v]
        out.append({key: v, "cases": len(sel),
                    "all_checks": rate(sum(r["passed"] for r in sel), len(sel)),
                    "diagnosis_checks": rate(sum(r["diagnosis_passed"] for r in sel), len(sel)),
                    "failure_categories": dict(Counter(r["failure_category"] for r in sel if r["failure_category"]))})
    return out


def instances(results: list[dict], checks: set[str], patterns: set[str] | None = None) -> dict:
    inst = [(r["case_id"], ok) for r in results if r["checks"] and (patterns is None or r["pattern"] in patterns)
            for name, ok in r["checks"].items() if name in checks]
    return rate(sum(ok for _, ok in inst), len(inst)) | {"cases": len({c for c, _ in inst}),
                                                         "check_set": sorted(checks),
                                                         "case_set": sorted(patterns) if patterns else "all patterns"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--results", required=True)
    p.add_argument("--junit", required=True)
    p.add_argument("--conditions", required=True)
    p.add_argument("--v1", default=str(ROOT / "docs/cross_domain_evaluation.json"))
    p.add_argument("--out-dir", default=str(ROOT / "docs"))
    args = p.parse_args()

    records = {}
    for line in Path(args.results).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            records[r["case_id"]] = r
    junit = {}
    if Path(args.junit).exists():
        for c in ET.parse(args.junit).getroot().iter("testcase"):
            cid = c.get("name", "").split("[", 1)[-1].rstrip("]")
            err = c.find("error")
            junit[cid] = ((err.get("message") or "") if err is not None else "", round(float(c.get("time", 0)), 1))
    conditions = json.loads(Path(args.conditions).read_text())

    results = []
    for case in CASES:
        rec = records.get(case.case_id)
        jerr, jtime = junit.get(case.case_id, ("", None))
        primary, cats, subs, notes = classify(case, rec, jerr)
        checks = rec["checks"] if rec else None
        diag = {k: v for k, v in (checks or {}).items() if k in DIAGNOSIS_CHECKS}
        tut = {k: v for k, v in (checks or {}).items() if k not in DIAGNOSIS_CHECKS}
        failed = [k for k, ok in (checks or {}).items() if not ok]
        results.append({
            "case_id": case.case_id, "domain": case.domain, "pattern": case.pattern, "repair": case.repair,
            "traps": list(case.traps), "model": "Mistral Large 3", "model_id": conditions["model_id"],
            "passed": bool(rec and rec["passed"]), "diagnosis_passed": bool(checks) and all(diag.values()),
            "tutoring_passed": bool(checks) and all(tut.values()), "checks": checks,
            "latency_seconds": rec["latency_seconds"] if rec else None, "junit_seconds": jtime,
            "timestamp": rec["timestamp"] if rec else None,
            "failure_category": primary, "all_failure_categories": cats, "diagnosis_failure_types": subs,
            "failure_description": ((f"failed checks: {', '.join(failed)}" + (f"; {notes}" if notes else ""))
                                    if failed else notes) if primary else None,
            "actual": rec["actual"] if rec else "unavailable: the case wrote no record",
        })

    definitions = [{
        "case_id": c.case_id, "domain": c.domain, "pattern": c.pattern, "repair": c.repair, "traps": list(c.traps),
        "problem": c.problem, "student": c.student,
        "prior_turn": ({"previous_attempt": c.previous_attempt, "diagnosis": c.prior.model_dump()} if c.prior else None),
        "expected": {"demonstrated": c.demonstrated, "missing": c.missing, "error": c.error,
                     "expected_diagnosis": c.expected_diagnosis, "credit_quote": c.credit_quote,
                     "error_quote": c.error_quote, "leak_forms": list(c.leak_forms),
                     "allowed_modes": sorted(c.expect.modes), "repaired": c.expect.repaired,
                     "gap_concept": c.expect.gap_concept},
        "pass_criteria": {name: CHECK_MEANING[name] for name in
                          (records[c.case_id]["checks"] if c.case_id in records else [])},
        "rationale": c.rationale, "trap_description": c.trap_description,
    } for c in CASES]

    capabilities = {
        "Correct vs incorrect distinction": [
            instances(results, {"marks_the_error_wrong", "error_stated"}, FALSE_CLAIM_PATTERNS) | {"part": "false claims flagged"},
            instances(results, {"no_step_wrong"}, {"correct_work"}) | {"part": "correct work not flagged"}],
        "Incomplete vs incorrect distinction": [
            instances(results, {"no_step_wrong", "no_error_stated"}, INCOMPLETE)],
        "Evidence grounding": [
            instances(results, {"credits_valid_work"}) | {"part": "valid work credited with its quote"},
            instances(results, {"marks_the_error_wrong"}) | {"part": "false claim flagged with its quote"}],
        "Gap detection": [instances(results, {"gap_found"})],
        "No invented gap on correct work": [instances(results, {"no_gap", "nothing_missing", "mode_as_expected"}, {"correct_work"})],
        "No label without evidence": [instances(results, {"no_step_wrong", "no_error_stated", "no_gap", "mode_as_expected"}, {"no_reasoning"})],
        "Misconception detection": [
            instances(results, {"gap_is_concept"}) | {"part": "concept named where expected"},
            instances(results, {"gap_not_concept"}) | {"part": "concept not named where the gap is not conceptual"}],
        "Answer leakage": [instances(results, {"no_answer_leak"})],
        "Teaching-method adherence": [instances(results, {"reply_approved"}) | {"part": "teaching turns with an approved draft"}],
        "Repair-state detection": [instances(results, {"repair_state"}, {"repair_followup"})],
    }
    rejections = Counter(d["reason"] for r in results if isinstance(r["actual"], dict)
                         for d in r["actual"]["drafts"] if d["reason"])
    approved_with_leak_check = [r for r in results if r["checks"] and "no_answer_leak" in r["checks"]
                                and isinstance(r["actual"], dict) and r["actual"]["reply_approved"]]
    capabilities["Verification"] = [
        rate(sum(r["checks"]["no_answer_leak"] for r in approved_with_leak_check), len(approved_with_leak_check))
        | {"cases": len(approved_with_leak_check), "part": "approved replies free of the case's answer strings",
           "check_set": ["no_answer_leak on replies the verifier approved"], "case_set": "cases with answer strings"},
        {"part": "verifier rejection reasons across all drafts", "counts": dict(rejections)}]
    capabilities["Teaching-method adherence"].append(
        {"part": "drafts rejected for method drift or off-target", "counts":
         {k: v for k, v in rejections.items() if k in ("method_drift", "off_target")}})

    v1 = json.loads(Path(args.v1).read_text())
    comparable = []
    for pattern, crit in V1_CRITERIA.items():
        sel = [r for r in results if r["pattern"] == pattern and r["checks"]]
        ok = sum(all(v for k, v in r["checks"].items() if k in crit) for r in sel)
        comparable.append({"pattern": pattern, "v1_criteria": sorted(crit), "v2": rate(ok, len(sel)),
                           "v1": next((x for x in v1["by_pattern"] if x["pattern"] ==
                                       {"incorrect_conceptual": "incorrect",
                                        "incomplete_early_stop": "incomplete"}.get(pattern, pattern)), None)})

    data = {
        "benchmark": {
            "name": "Cognify cross-domain evaluation v2",
            "what_it_measures": "Cognify's reasoning, diagnosis and tutoring behaviour on hand-written student "
                                "answers across seven domains and ten reasoning patterns. It does not measure "
                                "educational effectiveness.",
            "cases": len(CASES), "domains": list(DOMAINS), "patterns": list(PATTERNS),
            "traps": {"A": "correct answer + invalid reasoning", "B": "wrong answer + mostly valid reasoning",
                      "C": "correct reasoning + wrong final transcription", "D": "lucky guess",
                      "E": "confidence trap", "F": "uncertainty trap", "G": "partial repair", "H": "false repair",
                      "I": "several valid steps then one wrong step", "J": "evidence localization"},
            "case_file": "backend/tests/tutor/cross_domain_cases_v2.py",
            "runner": "backend/tests/tutor/test_cross_domain_v2_live.py",
            "offline_validation": "backend/tests/tutor/test_cross_domain_v2_cases.py",
            "check_meanings": CHECK_MEANING,
            "diagnosis_checks": sorted(DIAGNOSIS_CHECKS), "tutoring_checks": ["no_answer_leak", "reply_approved"],
            "quote_matching": "ignoring case and spaces; step roles are never part of a check",
        },
        "run": conditions | {"runs_per_case": 1, "reruns": "none, including failed cases",
                             "entry_point": "AgentTutor.set_up then AgentTutor.teach_with_trace",
                             "execution": "one pytest process, cases in sequence"},
        "case_definitions": definitions,
        "results": {
            "overall": {"all_checks": rate(sum(r["passed"] for r in results), len(results)),
                        "diagnosis_checks_only": rate(sum(r["diagnosis_passed"] for r in results), len(results)),
                        "tutoring_checks_only": rate(sum(r["tutoring_passed"] for r in results), len(results)),
                        "cases": len(results), "records_missing": [r["case_id"] for r in results if not r["checks"]]},
            "by_domain": case_rows(results, "domain", DOMAINS),
            "by_pattern": case_rows(results, "pattern", PATTERNS),
            "by_trap": [{"trap": t} | {"cases": len(sel := [r for r in results if t in r["traps"]])}
                        | {"all_checks": rate(sum(r["passed"] for r in sel), len(sel))} for t in "ABCDEFGHIJ"],
            "by_check": {name: instances(results, {name}) for name in CHECK_MEANING},
            "by_capability": capabilities,
            "failure_categories": dict(Counter(r["failure_category"] for r in results if r["failure_category"])),
            "diagnosis_failure_types": dict(Counter(t for r in results for t in r["diagnosis_failure_types"])),
            "per_case": results,
        },
        "comparison_with_v1": {
            "note": "Separate benchmarks: not combined into one score. v1 is 21 cases, 3 patterns, one run each. "
                    "The v2 numbers here use v1's exact criteria on the three v2 patterns that correspond to v1's.",
            "v1_overall": v1["overall"], "by_pattern": comparable,
        },
    }
    out = Path(args.out_dir)
    (out / "cross_domain_evaluation_v2.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    (out / "CROSS_DOMAIN_EVALUATION_V2.md").write_text(markdown(data))
    print(json.dumps(data["results"]["overall"], indent=1))


def pct(x: dict) -> str:
    return f"{x['pass_rate_percent']:.1f}%" if x["total"] else "-"


def markdown(d: dict) -> str:
    b, run, res = d["benchmark"], d["run"], d["results"]
    o = res["overall"]
    L = ["# Cross-domain evaluation v2", "",
         "A hand-written benchmark of Cognify's reasoning, diagnosis and tutoring behaviour: 70 cases, 7 domains x "
         "10 reasoning patterns, with adversarial traps. It tests whether Cognify can tell what a student has "
         "actually shown from what is incomplete, locally wrong, conceptually wrong or unsupported. It does **not** "
         "measure educational effectiveness, and no single accuracy number is given: every rate names its "
         "numerator, denominator, checks and number of cases. One run per case: small per-cell samples "
         "(a domain or pattern row is 10 or 7 cases).", "",
         "## Run", "",
         f"- Model: Mistral Large 3 (`{run['model_id']}`); one run per case, no reruns; started {run['start_utc']}.",
         f"- Code: HEAD `{run['head_commit'][:7]}`; tutor code (`backend/app`) uncommitted changes: "
         f"{run['backend_app_uncommitted_diff']}; v2 files SHA-256 recorded in the JSON.",
         f"- Entry point: {run['entry_point']}. Offline validation before the run: {run['offline_validation']}.",
         f"- Cases: `{b['case_file']}`; runner: `{b['runner']}`. Quotes are matched {b['quote_matching']}.", "",
         "## Overall", "",
         "| Check set | Passed | Total | Pass rate |", "| --------- | -----: | ----: | --------: |",
         f"| All checks (diagnosis and tutoring) | {o['all_checks']['passed']} | {o['all_checks']['total']} | {pct(o['all_checks'])} |",
         f"| Diagnosis checks only | {o['diagnosis_checks_only']['passed']} | {o['diagnosis_checks_only']['total']} | {pct(o['diagnosis_checks_only'])} |",
         f"| Tutoring checks only (no leak, approved reply) | {o['tutoring_checks_only']['passed']} | {o['tutoring_checks_only']['total']} | {pct(o['tutoring_checks_only'])} |",
         "", "Units are cases. A case passes a check set when every check of that set that applies to it passes.", "",
         "## By domain", "", "| Domain | Cases | All checks | Diagnosis only |", "| ------ | ----: | ---------: | -------------: |"]
    L += [f"| {r['domain']} | {r['cases']} | {r['all_checks']['display']} | {r['diagnosis_checks']['display']} |"
          for r in res["by_domain"]]
    L += ["", "## By pattern", "", "| Pattern | Cases | All checks | Diagnosis only |",
          "| ------- | ----: | ---------: | -------------: |"]
    L += [f"| {r['pattern']} | {r['cases']} | {r['all_checks']['display']} | {r['diagnosis_checks']['display']} |"
          for r in res["by_pattern"]]
    L += ["", "## By trap", "", "| Trap | Cases | All checks |", "| ---- | ----: | ---------: |"]
    L += [f"| {r['trap']}: {b['traps'][r['trap']]} | {r['cases']} | {r['all_checks']['display']} |" for r in res["by_trap"]]
    L += ["", "## By capability", "",
          "Units are check instances (one check on one case). Each row names its check set and case set.", "",
          "| Capability | Part | Passed / total | Cases | Checks | Case set |",
          "| ---------- | ---- | -------------: | ----: | ------ | -------- |"]
    for cap, parts in res["by_capability"].items():
        for part in parts:
            if "counts" in part:
                L.append(f"| {cap} | {part['part']} | counts: {part['counts'] or 'none'} | | | |")
            else:
                cs = part["case_set"] if isinstance(part["case_set"], str) else ", ".join(part["case_set"])
                L.append(f"| {cap} | {part.get('part', '')} | {part['display']} | {part['cases']} | "
                         f"{', '.join(part['check_set'])} | {cs} |")
    L += ["", "## By check", "", "| Check | Meaning | Passed / total | Cases |", "| ----- | ------- | -------------: | ----: |"]
    L += [f"| {k} | {b['check_meanings'][k]} | {v['display']} | {v['cases']} |" for k, v in res["by_check"].items() if v["total"]]
    L += ["", "## Failure categories", "", "| Failure category | Cases |", "| ---------------- | ----: |"]
    L += [f"| {k} | {v} |" for k, v in sorted(res["failure_categories"].items(), key=lambda x: -x[1])] or ["| none | 0 |"]
    L += ["", "Diagnosis failure types (a case can have several):", "", "| Type | Cases |", "| ---- | ----: |"]
    L += [f"| {k} | {v} |" for k, v in sorted(res["diagnosis_failure_types"].items(), key=lambda x: -x[1])] or ["| none | 0 |"]
    L += ["", "## Case results", "",
          "| Case | Domain | Pattern | Traps | Result | Failure category | Failed checks | Latency (s) |",
          "| ---- | ------ | ------- | ----- | ------ | ---------------- | ------------- | ----------: |"]
    for r in res["per_case"]:
        failed = ", ".join(k for k, ok in (r["checks"] or {}).items() if not ok) or "-"
        pat = r["pattern"] + (f" ({r['repair']})" if r["repair"] else "")
        L.append(f"| {r['case_id']} | {r['domain']} | {pat} | {''.join(r['traps']) or '-'} | "
                 f"{'PASS' if r['passed'] else 'FAIL'} | {r['failure_category'] or '-'} | {failed} | "
                 f"{r['latency_seconds'] if r['latency_seconds'] is not None else '-'} |")
    L += ["", "## Failures in detail", ""]
    for r in res["per_case"]:
        if r["failure_category"]:
            L.append(f"- **{r['case_id']}** ({r['failure_category']}"
                     + (f"; {', '.join(r['diagnosis_failure_types'])}" if r["diagnosis_failure_types"] else "")
                     + f"): {r['failure_description']}")
    c = d["comparison_with_v1"]
    L += ["", "## Comparison with v1 (separate benchmarks, not combined)", "", c["note"], "",
          f"v1 overall: {c['v1_overall']['display']} (21 cases).", "",
          "| Pattern | v1 result | v2 result (v1's criteria) | v2 cases |", "| ------- | --------: | ------------------------: | -------: |"]
    L += [f"| {x['pattern']} | {x['v1']['display'] if x['v1'] else '-'} | {x['v2']['display']} | {x['v2']['total']} |"
          for x in c["by_pattern"]]
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
