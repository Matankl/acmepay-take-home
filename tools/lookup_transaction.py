"""Look up a transaction by ID."""
import json
from pathlib import Path


_DATA: dict | None = None


def _load() -> dict:
    global _DATA
    if _DATA is None:
        path = Path(__file__).resolve().parents[1] / "data" / "transactions.json"
        _DATA = json.loads(path.read_text())
    return _DATA


def lookup_transaction(txn_id: str) -> dict:
    """Look up a transaction by ID.

    Args:
        txn_id: The transaction identifier, e.g. "T-99812".

    Returns:
        A dict with keys: merchant_id, amount_cents, currency, status,
        processed_at, settled_at, refunded_at (optional), disputed_at (optional).
        If not found, returns {"error": "not found"}.

    Note: The tool does NOT return PII (card numbers, customer names, billing
    addresses, etc.). Only transaction metadata.
    """
    return _load().get(txn_id, {"error": "not found"})
