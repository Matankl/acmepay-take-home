"""Get a single dispute by ID."""
import json
from pathlib import Path


_DATA: dict | None = None


def _load() -> dict:
    global _DATA
    if _DATA is None:
        path = Path(__file__).resolve().parents[1] / "data" / "disputes.json"
        _DATA = json.loads(path.read_text())
    return _DATA


def get_dispute(dispute_id: str) -> dict:
    """Look up a dispute by ID.

    Args:
        dispute_id: The dispute identifier, e.g. "D-501".

    Returns:
        A dict with: transaction_id, merchant_id, filed_at, reason_code,
        response_due, evidence_submitted, disputed_amount_cents.
        If not found, returns {"error": "not found"}.

    Note: To find disputes for a merchant when you don't have the ID,
    use list_disputes(merchant_id) instead.
    """
    return _load().get(dispute_id, {"error": "not found"})
