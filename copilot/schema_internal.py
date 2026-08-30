"""The internal draft schema, projected down to the frozen `Response`.

Every field here has to earn its place: it must be consumed by a validator or by
the projection. If it has neither, it is indirection and gets deleted.

  disposition    -> projects to `refused`; makes the three-way distinction a
                    first-class decision instead of an accident of prose.
  verdict        -> forces bottom-line-first; spliced in if the model buries it.
  detail         -> the supporting explanation.
  key_facts      -> consumed by the groundedness validator and by citation
                    attribution. Turns hallucination detection into substring
                    search over the supplied context.
  sources        -> seeds citation attribution but is NOT trusted; filtered
                    against what was actually in context, which kills invented
                    document names.
  refusal_reason -> projects straight through when declining.

Deliberately absent: `tool_calls`. The runtime owns that field.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Disposition = Literal["ANSWER", "DECLINE_ACTION", "DECLINE_BOUNDARY"]


class Draft(BaseModel):
    disposition: Disposition = Field(
        description=(
            "ANSWER for anything you can report on -- including 'no such record' "
            "and 'the policies are silent'. DECLINE_ACTION when asked to perform "
            "a state change. DECLINE_BOUNDARY when asked for something Acmepay "
            "categorically does not hold, or for a judgement outside its remit."
        )
    )
    verdict: str = Field(
        description=(
            "One sentence that answers the question directly. No preamble, no "
            "hedging. If the question is yes/no, start with the answer."
        )
    )
    detail: str = Field(
        default="",
        description="Supporting explanation, figures and next steps. May be empty.",
    )
    key_facts: list[str] = Field(
        default_factory=list,
        description=(
            "Every factual claim the answer makes, one per item, copied verbatim "
            "from the supplied policy text or record fields."
        ),
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Policy document filenames and record IDs this answer used.",
    )
    refusal_reason: Optional[str] = Field(
        default=None,
        description="Required when declining: what is being declined and why.",
    )

    @property
    def refused(self) -> bool:
        return self.disposition != "ANSWER"
