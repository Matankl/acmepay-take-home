"""Parallel eval sweep across every suite, with telemetry.

`evals/runner.py` is left exactly as shipped -- it is the grading entry point and
nothing here touches it. This is a separate development driver that imports the
same `grade()` and runs cases through a thread pool, because a serial sweep of
100 cases x N samples is slow enough to be the real constraint on how many
measured iterations fit in a working session.

    python -m scripts.sweep                      # all suites, 1 sample
    python -m scripts.sweep --samples 3          # strict-majority verdicts
    python -m scripts.sweep --suites tool_use    # one suite
    python -m scripts.sweep --baseline           # tag the run as the "before" column

Model responses are never cached. Caching them would make a majority-of-N vote
unanimous by construction and turn a reproducibility measure into a lie.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from evals.schema import CheckResult, EvalCase, CaseResult, grade

# Harness-level pacing, so that a system which does NOT pace itself is measured
# under the same rate limit as one that does. The copilot has its own token bucket
# (ACMEPAY_RPM); the untouched starter has none, and without this its "before"
# column would be measuring the provider's quota rather than the starter.
_RATE_LOCK = threading.Lock()
_next_slot = [0.0]
_rpm = [0]


def _pace() -> None:
    if _rpm[0] <= 0:
        return
    interval = 60.0 / _rpm[0]
    with _RATE_LOCK:
        now = time.monotonic()
        wait = max(0.0, _next_slot[0] - now)
        _next_slot[0] = max(now, _next_slot[0]) + interval
    if wait:
        time.sleep(wait)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "grade_artifacts"

DEFAULT_SUITES = [
    "factual_lookup", "multi_doc_synthesis", "refusals", "tool_use",
    "drafting", "investigation", "hallucination", "out_of_scope_actions",
]


def _load(name: str) -> list[EvalCase]:
    for path in (f"evals.{name}", f"evals.{name}_visible", f"_internal.evals_holdout.{name}"):
        try:
            mod = importlib.import_module(path)
        except ImportError:
            continue
        cases = getattr(mod, "CASES", None)
        if cases:
            return cases
    raise SystemExit(f"could not load suite {name!r}")


def _run_case(case: EvalCase, samples: int, module: str = "system") -> tuple[CaseResult, dict]:
    system = importlib.import_module(module)
    runs, telemetry = [], []
    for _ in range(samples):
        _pace()
        try:
            response = system.ask(case.question)
            runs.append(grade(case, response))
        except Exception as exc:                      # ask() should never raise
            runs.append(CaseResult(case.id, False,
                                   [CheckResult("system_error", False, f"{type(exc).__name__}: {exc}")]))
        getter = getattr(system, "last_telemetry", None)
        telemetry.append(getter() if getter else {})

    n_pass = sum(1 for r in runs if r.passed)
    passed = n_pass * 2 > samples if samples > 1 else runs[0].passed
    rep = next((r for r in runs if r.passed == passed), runs[-1])
    checks = ([CheckResult("samples", passed, f"{n_pass}/{samples} runs passed")] if samples > 1 else []) + rep.checks
    agg: dict = defaultdict(float)
    for t in telemetry:
        for k, v in t.items():
            if isinstance(v, (int, float)):
                agg[k] += v
    return CaseResult(case.id, passed, checks), dict(agg)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suites", nargs="*", default=DEFAULT_SUITES)
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--baseline", action="store_true", help='tag output as the "before" run')
    p.add_argument("--tag", default=None,
                   help="artifact name; defaults to baseline/current. Use an explicit "
                        "tag so separate experiments do not overwrite each other.")
    p.add_argument("--rpm", type=int, default=0,
                   help="harness-level requests/minute cap (use for systems that "
                        "do not pace themselves, e.g. the starter)")
    p.add_argument("--system", default="system", help="module exposing ask(); use scripts.baseline_system for the starter")
    p.add_argument("--out-dir", default=None,
                   help="artifact directory; defaults to grade_artifacts/. Use a "
                        "subdirectory to keep one provider's results from "
                        "overwriting another's.")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    _rpm[0] = args.rpm
    started = time.perf_counter()
    per_category: dict[str, list[CaseResult]] = {}
    totals: dict = defaultdict(float)
    failures: list[tuple[str, CaseResult]] = []
    # Per-case fallback counts. An aggregate count tells you a run is degraded but
    # not WHICH cases -- and a long sweep tends to degrade only at the tail, once a
    # daily quota runs out. Recording it per case means the clean prefix of an
    # expensive run is still a valid measurement instead of being thrown away.
    per_case_degraded: dict[str, int] = {}

    for suite in args.suites:
        cases = _load(suite)[: args.limit]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            pairs = list(pool.map(lambda c: _run_case(c, args.samples, args.system), cases))
        results = [r for r, _ in pairs]
        per_category[suite] = results
        for _, tel in pairs:
            for k, v in tel.items():
                totals[k] += v
        for case, (res, tel) in zip(cases, pairs):
            per_case_degraded[res.case_id] = int(tel.get("error_count", 0))
            if not res.passed:
                failures.append((case.question, res))

        n = sum(1 for r in results if r.passed)
        print(f"{suite:24} {n:3}/{len(results):<3} ({100*n/max(len(results),1):5.1f}%)")

    passed = sum(sum(1 for r in v if r.passed) for v in per_category.values())
    total = sum(len(v) for v in per_category.values())
    wall = time.perf_counter() - started
    print("-" * 46)
    print(f"{'TOTAL':24} {passed:3}/{total:<3} ({100*passed/max(total,1):5.1f}%)")
    print(f"\nwall {wall:.1f}s | llm calls {int(totals['llm_calls'])} | "
          f"repairs {int(totals['repairs'])} | tool calls {int(totals['tool_calls'])}")
    print(f"prompt tok {int(totals['prompt_tokens']):,} | cached tok "
          f"{int(totals['cached_tokens']):,} | completion tok {int(totals['completion_tokens']):,}")
    print(f"cost ${totals['cost_usd']:.4f}")
    degraded = int(totals.get("error_count", 0))
    expected = total * args.samples
    if degraded:
        print(f"\n!! {degraded} of {expected} generations fell back to the "
              f"deterministic path (provider errors).")
        if degraded > expected * 0.05:
            print("!! THIS RUN IS NOT A VALID MEASUREMENT of the system -- it is "
                  "mostly measuring the provider quota. Re-run with a lower --rpm "
                  "or after the limit resets.")

    if args.verbose and failures:
        print("\n-- failures --")
        for question, res in failures:
            print(f"[FAIL] {res.case_id}  {question!r}")
            for c in res.failed_checks:
                print(f"        x {c.name}" + (f"  ({c.detail})" if c.detail else ""))

    out_dir = Path(args.out_dir) if args.out_dir else ARTIFACTS
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = args.tag or ("baseline" if args.baseline else "current")
    out = {
        "tag": tag,
        "system": args.system,
        "model": os.environ.get("LLM_MODEL", "(unset)"),
        "suites": list(args.suites),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "samples": args.samples,
        "per_category": {k: {"passed": sum(1 for r in v if r.passed), "total": len(v)}
                         for k, v in per_category.items()},
        "total": {"passed": passed, "total": total},
        "telemetry": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in totals.items()},
        "wall_seconds": round(wall, 1),
        "degraded_generations": degraded,
        "valid_measurement": degraded <= total * args.samples * 0.05,
        "failed_case_ids": sorted(r.case_id for _, r in failures),
        "per_case": {r.case_id: r.passed
                     for v in per_category.values() for r in v},
        "per_case_degraded": per_case_degraded,
        "clean_cases": {
            "passed": sum(1 for v in per_category.values() for r in v
                          if r.passed and not per_case_degraded.get(r.case_id)),
            "total": sum(1 for v in per_category.values() for r in v
                         if not per_case_degraded.get(r.case_id)),
        },
    }
    (out_dir / f"sweep-{tag}.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    return total - passed


if __name__ == "__main__":
    raise SystemExit(main())
