"""List disputes for a merchant."""
import json
from pathlib import Path


_DATA: dict | None = None


def _load() -> dict:
    global _DATA
    if _DATA is None:
        path = Path(__file__).resolve().parents[1] / "data" / "disputes.json"
        _DATA = json.loads(path.read_text())
    return _DATA


def list_disputes(merchant_id: str) -> list[dict]:
    """List disputes for a merchant.

    Args:
        merchant_id: The merchant identifier, e.g. "M-1003".

    Returns:
        A list of dispute dicts, each with: dispute_id, transaction_id,
        filed_at, reason_code, response_due, evidence_submitted,
        disputed_amount_cents.
        Returns [] if the merchant has no disputes.
    """
    all_disputes = _load()
    out = []
    for d_id, d in all_disputes.items():
        if d["merchant_id"] == merchant_id:
            out.append({"dispute_id": d_id, **d})
    return out
