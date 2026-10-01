"""Run the 14 live tutor cases several times, in parallel, and print a pass-rate table.

The runs are independent pytest processes started together, so the total time is about one run.

    docker compose exec backend python -m scripts.eval_live            # 3 runs
    docker compose exec backend python -m scripts.eval_live --runs 5
"""

import argparse
import os
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

CASES = "tests/tutor/test_cases_live.py"


def start(path: str) -> subprocess.Popen:
    return subprocess.Popen(
        ["python", "-m", "pytest", "-m", "live", CASES, "-q", "-p", "no:cacheprovider", f"--junitxml={path}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


FAILURES: list[tuple[int, str, str]] = []


def read(path: str, run: int) -> dict[str, bool]:
    results = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        name = case.get("name", "").removeprefix("test_")
        problem = case.find("failure") if case.find("failure") is not None else case.find("error")
        results[name] = problem is None and case.find("skipped") is None
        if problem is not None:
            FAILURES.append((run, name, (problem.get("message") or "").splitlines()[0][:220]))
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    print(f"model: {os.environ.get('TUTOR_MODEL_ID')}")

    runs, times = [], []
    with tempfile.TemporaryDirectory() as tmp:
        started = time.monotonic()
        paths = [f"{tmp}/run{i}.xml" for i in range(args.runs)]
        procs = [start(path) for path in paths]
        print(f"started {args.runs} runs in parallel...", flush=True)
        for i, (proc, path) in enumerate(zip(procs, paths)):
            proc.wait()
            elapsed = time.monotonic() - started
            results = read(path, i + 1)
            runs.append(results)
            times.append(elapsed)
            print(f"run {i + 1}: {sum(results.values())}/{len(results)} passed, done after {elapsed:.0f}s", flush=True)

    names = sorted({n for r in runs for n in r})
    header = "| Case | " + " | ".join(f"Run {i + 1}" for i in range(args.runs)) + " | Pass rate |"
    print("\n" + header + "\n|" + "---|" * (args.runs + 2))
    for name in names:
        marks = [("pass" if r.get(name) else "FAIL") for r in runs]
        print(f"| {name} | " + " | ".join(marks) + f" | {sum(r.get(name, False) for r in runs)}/{args.runs} |")
    totals = [sum(r.values()) for r in runs]
    print(f"| **total** | " + " | ".join(f"{t}/{len(names)}" for t in totals) + f" | {sum(totals)}/{len(names) * args.runs} |")
    if FAILURES:
        print("\nfailures:")
        for run, name, message in sorted(FAILURES, key=lambda f: (f[1], f[0])):
            print(f"  run {run} {name}: {message}")
    print(f"\nwall time {max(times):.0f}s for {args.runs} parallel runs (each run finished after: "
          f"{' / '.join(f'{t:.0f}s' for t in times)})")


if __name__ == "__main__":
    main()
