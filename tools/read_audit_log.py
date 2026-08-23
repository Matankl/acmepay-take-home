"""Read audit log events for a specific merchant."""
import json
from pathlib import Path


_DATA: list[dict] | None = None


def _load() -> list[dict]:
    global _DATA
    if _DATA is None:
        path = Path(__file__).resolve().parents[1] / "data" / "audit_log.jsonl"
        _DATA = [
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]
    return _DATA


def read_audit_log(
    merchant_id: str,
    since: str | None = None,
    event_type: str | None = None,
) -> list[dict]:
    """Read audit-log events for a single merchant.

    Args:
        merchant_id: Required. The merchant identifier, e.g. "M-1003".
                     The log is ALWAYS scoped to this merchant; you cannot
                     pull cross-merchant data with this tool.
        since: Optional ISO date (YYYY-MM-DD). Returns events on or after this date.
        event_type: Optional event type filter, e.g. "dispute_filed",
                    "chargeback_ratio_warning", "payout_failed".

    Returns:
        A list of event dicts, oldest first. Each has timestamp, event_type,
        merchant_id, and optionally transaction_id, dispute_id, metadata.
        Returns [] if no matching events.

    Note: This tool is intentionally merchant-scoped. To investigate cross-merchant
    patterns you must call it per merchant — by design, to enforce access discipline.
    """
    events = [e for e in _load() if e.get("merchant_id") == merchant_id]
    if since:
        events = [e for e in events if e["timestamp"][:10] >= since]
    if event_type:
        events = [e for e in events if e["event_type"] == event_type]
    return events
