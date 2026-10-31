"""The no-LLM check: every labelled Alert, what the Typologies require. Free, so it runs each time."""

from collections import defaultdict
from typing import Any

from contracts import OtpFact
from typology.check import events_to_read, prove
from typology.engine import load_rules

PHRASE = "passed OTP"


def phrase_read(events: list[dict[str, Any]]) -> list[OtpFact]:
    """The baseline the LLM reader has to beat."""
    return [OtpFact(event_id=e["event_id"], otp_verified=True, quote=PHRASE)
            for e in events if PHRASE in (e.get("details") or "")]


def alert_subject(alert) -> str:
    return alert.transaction_id or alert.application_id or alert.claim_id or alert.device_id or alert.account_id


def run_sweep(store, held_out: set[str]) -> dict[str, Any]:
    """Each Alert alone. Fraud on an account the same week can correctly touch a benign Alert."""
    labels = {g["subject_id"]: g for g in store.ground_truth()}
    rules = load_rules()
    rows: dict[str, dict[str, Any]] = defaultdict(lambda: {"alerts": 0, "suspicious": 0, "not_suspicious": 0, "none": 0})
    wrong = []
    accounts = store.account_rows()
    for alert in store.all_alerts():
        subject = alert_subject(alert)
        label = labels.get(subject)
        if label is None or subject in held_out:
            continue
        records = store.records_for_alerts([alert], accounts[alert.account_id]["portfolio"])
        result, _ = prove(records, phrase_read(events_to_read(records)), rules)
        row = rows[label["story"]]
        row["fraud"] = bool(label["is_fraud"])
        row["alerts"] += 1
        row[result.requirement] += 1
        if (label["is_fraud"] and result.requirement == "not_suspicious") or (
            not label["is_fraud"] and result.requirement == "suspicious"
        ):
            wrong.append({"subject": subject, "story": label["story"], "requirement": result.requirement,
                          "typologies": sorted({p.typology for p in result.proofs})})
    return {"stories": dict(rows), "wrong": wrong}
