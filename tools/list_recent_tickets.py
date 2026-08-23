"""List recent tickets for a merchant (metadata only)."""
import re
from pathlib import Path


_TICKETS_DIR = Path(__file__).resolve().parents[1] / "data" / "tickets"
_CACHE: list[dict] | None = None


def _parse_ticket_metadata(path: Path) -> dict:
    """Parse only the metadata header from a ticket file."""
    text = path.read_text()
    # Subject is the first line after "# TKT-NNN —"
    ticket_id_match = re.search(r"# (TKT-\d+)\s*—\s*(.*)", text)
    merchant_match = re.search(r"\*\*(?:Merchant|Applicant):\*\*\s*(M-\d+)", text)
    opened_match = re.search(r"\*\*Opened:\*\*\s*([\d\-]+)", text)
    closed_match = re.search(r"\*\*Closed:\*\*\s*([\d\-]+|—)", text)
    status_match = re.search(r"\*\*Status:\*\*\s*([^\n]+)", text)

    return {
        "ticket_id": ticket_id_match.group(1) if ticket_id_match else path.stem,
        "subject": ticket_id_match.group(2).strip() if ticket_id_match else "",
        "merchant_id": merchant_match.group(1) if merchant_match else None,
        "opened_at": opened_match.group(1) if opened_match else None,
        "closed_at": (
            None if (closed_match and closed_match.group(1) == "—")
            else (closed_match.group(1) if closed_match else None)
        ),
        "status": status_match.group(1).strip() if status_match else "unknown",
    }


def _all_tickets() -> list[dict]:
    global _CACHE
    if _CACHE is None:
        _CACHE = [_parse_ticket_metadata(p) for p in sorted(_TICKETS_DIR.glob("*.md"))]
    return _CACHE


def list_recent_tickets(merchant_id: str) -> list[dict]:
    """List tickets for a merchant (metadata only).

    Args:
        merchant_id: The merchant identifier, e.g. "M-1001".

    Returns:
        A list of dicts, each with: ticket_id, subject, opened_at, closed_at, status.
        Returns [] if the merchant has no tickets.

    Note: This returns METADATA only — to read the ticket body, call get_ticket.
    """
    return [t for t in _all_tickets() if t["merchant_id"] == merchant_id]
