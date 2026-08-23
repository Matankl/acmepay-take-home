"""Look up a merchant by ID."""
import json
from pathlib import Path


_DATA: dict | None = None


def _load() -> dict:
    global _DATA
    if _DATA is None:
        path = Path(__file__).resolve().parents[1] / "data" / "merchants.json"
        _DATA = json.loads(path.read_text())
    return _DATA


def lookup_merchant(merchant_id: str) -> dict:
    """Look up a merchant by ID.

    Args:
        merchant_id: The merchant identifier, e.g. "M-1001".

    Returns:
        A dict with keys: name, plan, signup_date, volume_bucket, status,
        chargeback_ratio_30d, on_extended_settlement, rolling_reserve_pct,
        account_flags, city, state.
        If not found (e.g. rejected applicants), returns {"error": "not found"}.

    Note: Rejected applicants (e.g. M-1006) do NOT appear in merchants.json
    even though they may appear in the audit log as rejected_applicant events.
    """
    return _load().get(merchant_id, {"error": "not found"})
