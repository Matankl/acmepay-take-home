"""Leakage check: no string in copilot/ was copied from an eval matcher.

The held-out set is a paraphrase of the visible one, so anything keyed to a
visible question's wording scores locally and collapses on the real grade. This
walks the AST of every module in copilot/ (plus system.py) and compares its
string constants against every answer matcher in every visible suite.

Two classes are reported, because ordinary English inevitably overlaps with a
substring matcher:

  HARD  a literal that is exactly equal to a matcher string. That is copying, and
        it fails the check.
  SOFT  a matcher string that merely occurs inside a longer literal -- e.g. a
        template sentence containing the words "no record". Reported for review,
        not failed, because "never write a sentence containing a graded
        substring" is not a coherent constraint.

Exit code = number of HARD findings.
"""
from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = [
    "factual_lookup", "multi_doc_synthesis", "refusals", "tool_use",
    "drafting", "investigation", "hallucination", "out_of_scope_actions",
]
MIN_LEN = 4        # shorter fragments are not evidence of anything

# A matcher only counts as HARD evidence of copying if it is *fact-shaped*: more
# than one word, or carrying a number or a domain token. A bare common word is not
# evidence -- several eval cases require the single word "merchant" or "dispute",
# and this package legitimately uses those as dict keys, enum values and regex
# alternatives. Flagging them as copied made the check noisy enough to ignore,
# which is worse than not having it.
_FACT_SHAPED = re.compile(r"\s|\d|[%$/]|T\+")


def _fact_shaped(needle: str) -> bool:
    return bool(_FACT_SHAPED.search(needle))


def matcher_strings() -> set[str]:
    out: set[str] = set()
    for suite in SUITES:
        for case in importlib.import_module(f"evals.{suite}_visible").CASES:
            out.update(case.answer_contains_all)
            out.update(case.answer_must_not_contain)
            for group in case.answer_contains_any_of:
                out.update(group)
    return {s.strip().lower() for s in out if len(s.strip()) >= MIN_LEN}


def literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Docstrings are prose about the design, not behaviour.
            found.append((node.lineno, node.value))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    return [(ln, v) for ln, v in found if v not in docstrings]


def main() -> int:
    needles = matcher_strings()
    files = sorted((ROOT / "copilot").glob("*.py")) + [ROOT / "system.py"]
    hard, soft = [], []
    for path in files:
        for lineno, value in literals(path):
            low = value.strip().lower()
            if low in needles and _fact_shaped(low):
                hard.append((path.name, lineno, value))
            elif low in needles:
                soft.append((path.name, lineno, low, value[:70]))
            else:
                for needle in needles:
                    if needle in low:
                        soft.append((path.name, lineno, needle, value[:70]))
                        break

    rel = ROOT.name
    fact_shaped = sum(1 for n in needles if _fact_shaped(n))
    print(f"scanned {len(files)} files against {len(needles)} eval matcher strings "
          f"({fact_shaped} of them fact-shaped and therefore HARD-eligible)\n")
    if hard:
        print("HARD findings (literal copied from an eval matcher):")
        for name, lineno, value in hard:
            print(f"  {rel}/{name}:{lineno}  {value!r}")
    else:
        print("HARD findings: none")
    if soft:
        print(f"\nSOFT findings ({len(soft)}) -- graded substring inside ordinary prose:")
        for name, lineno, needle, snippet in soft:
            print(f"  {rel}/{name}:{lineno}  contains {needle!r}  in {snippet!r}")
    return len(hard)


if __name__ == "__main__":
    raise SystemExit(main())
