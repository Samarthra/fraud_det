"""Reads one Text fact. A failure leaves the fact absent, so it can never clear a Case."""

import json
from typing import Any

from contracts import OtpDraft, OtpFact
from tools import wrap_untrusted


def message(events: list[dict[str, Any]]) -> str:
    rows = [{"event_id": e["event_id"], "details": e.get("details") or ""} for e in events]
    return json.dumps(wrap_untrusted(rows), ensure_ascii=False)


def keep(draft: OtpDraft, events: list[dict[str, Any]]) -> tuple[list[OtpFact], list[str]]:
    """Code decides what counts: a real event, a true value and the record's exact words."""
    by_id = {e["event_id"]: e.get("details") or "" for e in events}
    kept, problems = [], []
    for fact in draft.facts:
        if fact.event_id not in by_id:
            problems.append(f"The reader named an unknown event, {fact.event_id}.")
        elif fact.otp_verified and (not fact.quote.strip() or fact.quote not in by_id[fact.event_id]):
            problems.append(f"The reader's quote isn't in {fact.event_id}, so it was ignored.")
        elif fact.otp_verified:
            kept.append(fact)
    return kept, problems
