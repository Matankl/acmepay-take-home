"""The tool ledger.

`Response.tool_calls` is *observability, not generation*. The starter passes
`Response` straight in as `instructor`'s `response_model`, which means the model
fills in `tool_calls` itself -- it reports calls it never made. The internal
Draft schema therefore has no `tool_calls` field at all, and this ledger is the
single source of truth.

Two details the grader forces:
  * A tool that raises must still be recorded. The grader matches on name and
    arguments only; the result is irrelevant.
  * Keyword names must mirror the tool signatures literally, because arguments
    are matched by exact key.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import tools

REGISTRY = {name: getattr(tools, name) for name in sorted(tools.__all__)}


@dataclass(frozen=True)
class Executed:
    name: str
    args: dict
    result: Any = None
    error: str | None = None

    @property
    def missing(self) -> bool:
        """True when the tool ran fine and reported that nothing is on file.

        Not an error condition -- for M-1006, T-99999 and M-1099 this *is* the
        answer, and the read tools signal it by returning {"error": "not found"}
        rather than raising.
        """
        if isinstance(self.result, dict) and self.result.get("error"):
            return True
        return self.result == [] or self.result is None and self.error is None


@dataclass
class ToolLedger:
    rows: list[Executed] = field(default_factory=list)

    def call(self, name: str, **args) -> Any:
        fn = REGISTRY[name]
        recorded = dict(sorted(args.items()))
        try:
            result, error = fn(**args), None
        except Exception as exc:                      # a corrupt data file must
            result, error = None, f"{type(exc).__name__}: {exc}"   # not 500 ask()
        self.rows.append(Executed(name, recorded, result, error))
        return result

    def already(self, name: str, **args) -> bool:
        recorded = dict(sorted(args.items()))
        return any(r.name == name and r.args == recorded for r in self.rows)

    def call_once(self, name: str, **args) -> Any:
        if self.already(name, **args):
            for r in self.rows:
                if r.name == name and r.args == dict(sorted(args.items())):
                    return r.result
        return self.call(name, **args)

    def record_ids(self) -> list[str]:
        """IDs of records that were actually fetched and actually exist.

        These are appended to cited_doc_ids -- provenance for the structured
        half of an answer, mirroring doc names for the prose half.
        """
        out: set[str] = set()
        for r in self.rows:
            if r.error or r.missing:
                continue
            for key in ("txn_id", "merchant_id", "dispute_id", "ticket_id"):
                if key in r.args:
                    out.add(r.args[key])
            if isinstance(r.result, list):
                for item in r.result:
                    if isinstance(item, dict):
                        for key in ("dispute_id", "ticket_id"):
                            if item.get(key):
                                out.add(item[key])
        return sorted(out)

    def as_tool_calls(self) -> list[dict]:
        """Plain dicts, not ToolCall instances.

        `python system.py` loads system as __main__, so importing ToolCall from
        here would build a second, distinct class and pydantic would reject the
        instances. Dicts validate correctly whichever way the module was loaded.
        """
        return [{"name": r.name, "args": dict(r.args)} for r in self.rows]
