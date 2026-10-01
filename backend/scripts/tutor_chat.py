"""Manual tutor test: type as the student and watch every stage of a real Master session.

    docker compose exec backend python -m scripts.tutor_chat            # interactive, Maria, ball problem
    docker compose exec backend python -m scripts.tutor_chat --demo     # premade Maria story, no typing
    docker compose exec backend python -m scripts.tutor_chat --custom   # your own problem and solution
    docker compose exec backend python -m scripts.tutor_chat --matrix   # matrix problem, opening attempt sent for you
    docker compose exec backend python -m scripts.tutor_chat --student nikos --force-experiment

It runs SessionService (the real flow and history writes) with the real AgentTutor on a
fresh seeded in-memory store.
Commands while chatting: /json shows the last turn's trace, /quit ends.
"""

import argparse
import asyncio
import time

from app.history import InMemoryHistory
from app.seed import seed_store
from app.session.schema import SessionStartRequest, Solution, VerdictTurn
from app.tutor.agent import AgentTutor
from app.user.ports import ProblemSetup
from app.user.service import SessionService

from .scenarios import BALL_PROBLEM, MARIA_TURNS, MATRIX_ATTEMPT, MATRIX_PROBLEM, STUDENTS

BOLD, DIM, RED, AMBER, GREEN, END = "\033[1m", "\033[2m", "\033[31m", "\033[33m", "\033[32m", "\033[0m"


class ChatTutor(AgentTutor):
    """The real tutor for this one chat, keeping the last turn's trace for display."""

    def __init__(self, store, solution: Solution | None = None):
        super().__init__(store, on_trace=self._keep)
        self.last_trace = None
        self._custom = solution

    def _keep(self, trace) -> None:
        self.last_trace = trace

    async def set_up(self, problem, subject):
        if self._custom is None:
            return await super().set_up(problem, subject)
        return ProblemSetup(concept_name="Custom problem", solution=self._custom)


def show_trace(tutor: AgentTutor) -> None:
    trace = tutor.last_trace
    if trace is None:
        return
    d = trace.diagnosis
    print(f"{BOLD}[1 reasoning]{END} evidence {d.evidence} · confidence {d.confidence} · main gap {BOLD}{d.main_gap}{END}"
          + (f"  {RED}({trace.diagnosis_failure}){END}" if trace.diagnosis_failure else ""))
    for step in d.steps:
        colour = {"correct": GREEN, "wrong": RED, "missing": AMBER}[step.status]
        quote = f'  "{step.quote}"' if step.quote else ""
        print(f"    {colour}{step.status:<8}{END} {step.role:<20}{DIM}{quote}{END}")
    for dim in d.dimensions:
        print(f"    {dim.name:<16} {dim.state:<9} {DIM}{dim.evidence}{END}")
    print(f"{BOLD}[2 rules]{END} mode {BOLD}{trace.mode}{END} · gap step {trace.gap_step.role if trace.gap_step else '-'}"
          f" · repaired {trace.gap_repaired}" + (f" {DIM}({trace.repair_reason}){END}" if trace.repair_reason else ""))
    s = trace.strategy
    print(f"{BOLD}[3 choose_strategy]{END} " + (f"{s.method} ({s.mode}) · {s.reason}" if s else "no method (nothing to teach)"))
    for i, draft in enumerate(trace.drafts, 1):
        print(f"{BOLD}[4 teaching draft {i}]{END} {draft.reply or '-'}")
        if draft.check:
            verdict = f"{GREEN}approved{END}" if draft.check.approved else f"{RED}rejected: {draft.check.reason}{END}"
            print(f"{BOLD}[5 verifier]{END} {verdict}  {DIM}{draft.check.note}{END}")
        if draft.failure:
            print(f"{RED}[failure]{END} {draft.failure}")


def show_turn(turn, tutor: AgentTutor, seconds: float) -> None:
    if isinstance(turn, VerdictTurn):
        v = turn.verdict
        colour = GREEN if v.result == "VERIFIED" else AMBER
        print(f"\n{BOLD}── verdict ──{END} {colour}{v.result}{END} · independent {v.independent} · {DIM}{v.evidence}{END}")
        c = v.changes
        print(f"  concept {c.concept.name}: {c.concept.before} -> {c.concept.after}")
        if c.strategy:
            s = c.strategy
            print(f"  strategy {s.method} on {s.gap}: {s.before.independent_successes}/{s.before.uses}"
                  f" -> {s.after.independent_successes}/{s.after.uses}")
        print(f"{BOLD}Tutor:{END} {turn.message}\n{DIM}{seconds:.1f}s{END}\n")
        return
    print()
    show_trace(tutor)
    tutor.last_trace = None
    print(f"\n{BOLD}── to the student ({turn.phase}) ──{END}")
    print(f"{BOLD}Tutor:{END} {turn.message}")
    if turn.follow_up:
        print(f"{BOLD}Fresh problem:{END} {turn.follow_up.problem}")
    print(f"{DIM}hints used {turn.hints_used} · {turn.reply_check.summary} · {seconds:.1f}s{END}\n")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--student", choices=sorted(STUDENTS), default="maria")
    parser.add_argument("--custom", action="store_true", help="type your own problem and its solution")
    parser.add_argument("--demo", action="store_true", help="play the premade Maria story")
    parser.add_argument("--matrix", action="store_true", help="matrix problem; its opening attempt is sent for you")
    parser.add_argument("--force-experiment", action="store_true", help="make choose_strategy run an experiment")
    args = parser.parse_args()

    store = InMemoryHistory()
    seed_store(store)
    if args.custom:
        problem = input("Problem: ").strip()
        result = input("Final answer (e.g. 20.4 m): ").strip()
        steps = input("Worked solution in one line: ").strip()
        tutor = ChatTutor(store, Solution(result=result, steps=[steps or result]))
    else:
        problem = MATRIX_PROBLEM if args.matrix else BALL_PROBLEM
        tutor = ChatTutor(store)
    service = SessionService(tutor, store)
    start = await service.start(SessionStartRequest(
        problem=problem, student_id=STUDENTS[args.student], force_experiment=args.force_experiment))

    print(f"\n{BOLD}Student:{END} {args.student.title()} (seeded demo history)")
    print(f"{BOLD}Problem:{END} {problem}")
    print(f"{BOLD}Tutor:{END} {start.message}\n")

    scripted = iter(MARIA_TURNS if args.demo else [MATRIX_ATTEMPT] if args.matrix else [])
    while True:
        text = next(scripted, None)
        if text is not None:
            print(f"{BOLD}You:{END} {text}")
        elif args.demo:
            break
        else:
            try:
                text = input(f"{BOLD}You:{END} ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text == "/quit":
                break
            if text == "/json":
                print(tutor.last_trace.model_dump_json(indent=2) if tutor.last_trace else "No trace yet.")
                continue
        started = time.monotonic()
        print(f"{DIM}thinking: reasoning -> choose_strategy -> teaching -> verifier ...{END}")
        turn = await service.attempt(start.session_id, text)
        show_turn(turn, tutor, time.monotonic() - started)
        if isinstance(turn, VerdictTurn) and turn.session_over:
            break


if __name__ == "__main__":
    asyncio.run(main())
