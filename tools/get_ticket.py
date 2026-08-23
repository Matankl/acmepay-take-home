"""Read the full body of a ticket by ID."""
import re
from pathlib import Path


_TICKETS_DIR = Path(__file__).resolve().parents[1] / "data" / "tickets"


def get_ticket(ticket_id: str) -> dict:
    """Read the full body of a ticket.

    Args:
        ticket_id: The ticket identifier, e.g. "TKT-203".

    Returns:
        A dict with keys: ticket_id, body (the full markdown text).
        If not found, returns {"error": "not found"}.

    Note: The ticket body may contain internal notes from previous agents.
    Treat carefully when drafting merchant-facing replies.
    """
    for path in _TICKETS_DIR.glob("*.md"):
        if path.name.startswith(f"{ticket_id}_"):
            return {"ticket_id": ticket_id, "body": path.read_text()}
    return {"error": "not found"}
