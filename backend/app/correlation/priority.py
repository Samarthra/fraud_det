"""Ranks Cases on severity, money at risk, related events and confidence, all from code."""

from typing import Any

from contracts import Alert, Confidence, Priority, RiskLevel

from .consolidate import inr, subject_record

ANALYST_SEVERITY = {"low": 25, "medium": 60, "high": 90}
CONFIDENCE_SHARE = {"low": 0.3, "medium": 0.7, "high": 1.0}


def exposure(alerts: list[Alert]) -> float:
    """Money counted once: a transfer of loan proceeds is already in the loan's amount."""
    has_loan = any(a.application_id for a in alerts)
    total = 0.0
    seen: set[str] = set()
    for alert in alerts:
        subject = alert.transaction_id or alert.application_id or alert.claim_id
        if subject is None or subject in seen:
            continue
        seen.add(subject)
        if has_loan and any(h.rule == "loan_proceeds_transfer" for h in alert.rule_hits):
            continue
        total += float(subject_record(alert).get("amount") or 0)
    return total


def confidence(alerts: list[Alert]) -> Confidence:
    rules = {h.rule for a in alerts for h in a.rule_hits}
    if len(rules) >= 3 and (len(alerts) >= 2 or max(a.score for a in alerts) >= 75):
        return "high"
    return "medium" if len(rules) >= 2 else "low"


def assess(alerts: list[Alert], classified: RiskLevel | None, config: dict[str, Any]) -> Priority:
    """`classified` is the Analyst's risk level, when they have changed it."""
    settings = config["priority"]
    weights = settings["weights"]
    severity = ANALYST_SEVERITY[classified] if classified else max(a.score for a in alerts)
    money = exposure(alerts)
    related = len(alerts)
    trust = confidence(alerts)
    needs_review = trust == "low"  # one kind of signal, however many times it fired

    score = round(
        weights["severity"] * severity
        + weights["exposure"] * 100 * min(1.0, money / settings["exposure_cap"])
        + weights["events"] * 100 * min(1.0, related / settings["events_cap"])
        + weights["confidence"] * 100 * CONFIDENCE_SHARE[trust]
    )
    bands = settings["bands"]
    if needs_review:
        score = min(score, settings["needs_review_cap"])
        band = "needs_review"
    elif score >= bands["critical"]:
        band = "critical"
    elif score >= bands["high"]:
        band = "high"
    elif score >= bands["medium"]:
        band = "medium"
    else:
        band = "low"

    products = sorted({a.product.replace("_", " ") for a in alerts})
    rules = sorted({h.rule for a in alerts for h in a.rule_hits})
    source = f"the Analyst's {classified} classification" if classified else "the highest Alert score"
    reasons = [
        f"Severity {severity}, from {source}.",
        f"Financial exposure {inr(money)}." if money else "No amount at risk is recorded yet.",
        f"{related} related Alert(s) across {', '.join(products)}.",
        f"Confidence {trust}: {len(rules)} distinct rule(s) fired.",
    ]
    if needs_review:
        reasons.append("One signal alone isn't enough to rank this highly, so it needs further review.")
    return Priority(score=score, band=band, severity=severity, exposure=money, related_events=related,
                    confidence=trust, needs_review=needs_review, reasons=reasons)
