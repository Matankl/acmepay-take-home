"""Eval runner — loads a case suite, runs each through `system.ask`, grades, prints.

Usage:
    python -m evals.runner factual_lookup_visible
    python -m evals.runner factual_lookup_visible --limit 3       # first N cases
    python -m evals.runner factual_lookup_visible --verbose       # show each failed check
    python -m evals.runner factual_lookup_visible --ids 002,005   # only these case ids (suffix match)
    python -m evals.runner refusals_visible --samples 3           # majority of 3 runs (smooths gpt-5.x jitter)

Exit code = number of failures (so CI can gate on it later).
"""
from __future__ import annotations

import argparse
import importlib
import sys
from typing import Callable

from .schema import EvalCase, CaseResult, grade


def _load_suite(name: str) -> list[EvalCase]:
    """Load a CASES list from `evals.<name>` or `_internal.evals_holdout.<name>`."""
    candidates = [f"evals.{name}", f"_internal.evals_holdout.{name}"]
    last_err = None
    for mod_path in candidates:
        try:
            mod = importlib.import_module(mod_path)
            cases = getattr(mod, "CASES", None)
            if cases is None:
                raise AttributeError(f"{mod_path} has no CASES list")
            return cases
        except (ImportError, AttributeError) as e:
            last_err = e
            continue
    raise SystemExit(f"could not load suite '{name}' (tried {candidates}): {last_err}")


def _filter(cases: list[EvalCase], limit: int | None, ids: list[str] | None) -> list[EvalCase]:
    if ids:
        ids_set = set(ids)
        cases = [c for c in cases if any(c.id.endswith(i) for i in ids_set)]
    if limit:
        cases = cases[:limit]
    return cases


def _grade_once(case: EvalCase, ask_fn: Callable[[str], object]) -> CaseResult:
    try:
        response = ask_fn(case.question)
        return grade(case, response)
    except Exception as e:
        from .schema import CheckResult
        return CaseResult(
            case_id=case.id,
            passed=False,
            checks=[CheckResult("system_error", False, detail=f"{type(e).__name__}: {e}")],
        )


def run_suite(
    cases: list[EvalCase],
    ask_fn: Callable[[str], object],
    samples: int = 1,
) -> list[CaseResult]:
    """Grade each case. With samples>1, run each case N times and take the
    MAJORITY verdict (strict majority; ties count as fail). This is for the
    Azure gpt-5.x reasoning models, which only run at temperature=1 and so vary
    run to run — a single run isn't reproducible. Majority vote gives a stable,
    honest pass/fail without inflating like best-of-N would.
    """
    from .schema import CheckResult
    results: list[CaseResult] = []
    for case in cases:
        if samples <= 1:
            results.append(_grade_once(case, ask_fn))
            continue
        runs = [_grade_once(case, ask_fn) for _ in range(samples)]
        n_pass = sum(1 for r in runs if r.passed)
        final_passed = n_pass * 2 > samples  # strict majority; tie -> fail
        # Representative run for displaying failed checks: a failing run if the
        # case ultimately fails, else a passing run.
        rep = next((r for r in runs if r.passed == final_passed), runs[-1])
        checks = [CheckResult("samples", final_passed, detail=f"{n_pass}/{samples} runs passed")]
        checks.extend(rep.checks)
        results.append(CaseResult(case_id=case.id, passed=final_passed, checks=checks))
    return results


def print_results(cases: list[EvalCase], results: list[CaseResult], verbose: bool = False) -> None:
    by_id = {c.id: c for c in cases}
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        case = by_id.get(r.case_id)
        q = case.question if case else ""
        sample_note = next(
            (f"  [{c.detail}]" for c in r.checks if c.name == "samples"),
            "",
        )
        print(f"[{status}] {r.case_id}{sample_note}  {q!r}")
        if verbose or not r.passed:
            for check in r.failed_checks:
                detail = f"  ({check.detail})" if check.detail else ""
                print(f"        ✗ {check.name}{detail}")
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{passed}/{total} passed ({100 * passed / total if total else 0:.0f}%)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("suite", help="suite module name, e.g. factual_lookup_visible")
    p.add_argument("--limit", type=int, default=None, help="only run first N cases")
    p.add_argument("--ids", type=str, default=None, help="comma-separated case-id suffixes to run")
    p.add_argument("--verbose", action="store_true", help="show all checks, not just failures")
    p.add_argument(
        "--samples", type=int, default=1,
        help="run each case N times and take the majority verdict (smooths "
             "run-to-run nondeterminism on temperature-locked models, e.g. gpt-5.x)",
    )
    args = p.parse_args(argv)

    cases = _filter(
        _load_suite(args.suite),
        limit=args.limit,
        ids=args.ids.split(",") if args.ids else None,
    )
    if not cases:
        print("No cases matched filters.", file=sys.stderr)
        return 0

    # Import lazily so loading the suite doesn't require an API key.
    from system import ask
    results = run_suite(cases, ask, samples=max(1, args.samples))
    print_results(cases, results, verbose=args.verbose)
    return sum(1 for r in results if not r.passed)


if __name__ == "__main__":
    raise SystemExit(main())
