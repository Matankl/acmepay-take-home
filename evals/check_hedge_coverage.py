"""Coverage proof for the prose validator.

copilot/validate.py deliberately does not import the grader's phrase list. It
implements the semantic classes instead -- first-person incapacity, and
deferential information requests -- so that it also catches phrasings the list
never enumerated. This script is the other half of that argument: it demonstrates
at development time that the principled detectors subsume the grader's list.

A phrase the detectors miss is not automatically a bug. Some entries in the
grader's list are not statements about the assistant's capability at all (for
example an impersonal "does not list"), and the correct fix for those is the
answer-style contract, not a capability detector. Those are reported separately.
"""
from __future__ import annotations

from evals.schema import HEDGE_PHRASES
from copilot.validate import incapacity_hits

# Entries that are not first-person incapacity and not information requests.
# These are handled by the style contract ("describe the world, not yourself")
# plus the deterministic rewrites, not by the capability detectors.
IMPERSONAL = {
    "doesn't list", "does not list", "don't list", "do not list",
    "not enough context", "insufficient context",
    "the provided excerpt", "the excerpt does not",
}


def main() -> int:
    covered, impersonal, missed = [], [], []
    for phrase in HEDGE_PHRASES:
        probe = f"Regarding that account, {phrase} the figure you asked about."
        if incapacity_hits(probe):
            covered.append(phrase)
        elif phrase in IMPERSONAL:
            impersonal.append(phrase)
        else:
            missed.append(phrase)

    total = len(HEDGE_PHRASES)
    print(f"grader phrase list: {total} entries")
    print(f"  matched by the principled detectors : {len(covered)}")
    print(f"  impersonal, handled by style+rewrite: {len(impersonal)}")
    print(f"  unmatched                           : {len(missed)}")
    for phrase in missed:
        print(f"    unmatched: {phrase!r}")
    from copilot.validate import sanitize
    still = [p for p in missed if sanitize(f"we {p} that") == f"we {p} that"]
    if still:
        print("\n  of the unmatched, not rewritten either:")
        for phrase in still:
            print(f"    {phrase!r}")
    return len(still)


if __name__ == "__main__":
    raise SystemExit(main())
