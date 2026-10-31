"""Deterministic checks. They prove facts match, not that the reasoning is right."""

import json
import re
from collections.abc import Iterable

from contracts import Evidence, ReportDraft

RECORD_ID = re.compile(r"\b(?:ACC|TXN|BEN|DEV|CUS|APP)-[A-Za-z0-9-]*\d")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# Small bare numbers such as "30-day" or "6 accounts" are not treated as amounts.
AMOUNT = re.compile(
    r"₹\s*\d[\d,]*(?:\.\d+)?|\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b|\b\d{3,}(?:\.\d+)?\b"
)
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _as_number(text: str) -> float:
    return float(re.sub(r"[₹,\s]", "", text))


def check_statement(statement: str, cited: Iterable[Evidence]) -> list[str]:
    blob = " ".join(f"{e.source_ref} {json.dumps(e.data, ensure_ascii=False)}" for e in cited)
    numbers = {float(n) for n in NUMBER.findall(blob)}
    errors = [
        f"{record_id} is not in the cited Evidence."
        for record_id in sorted(set(RECORD_ID.findall(statement)))
        if record_id not in blob
    ]
    errors += [
        f"Date {date} is not in the cited Evidence."
        for date in sorted(set(DATE.findall(statement)))
        if date not in blob
    ]
    remainder = DATE.sub(" ", RECORD_ID.sub(" ", statement))
    errors += [
        f"Amount {amount.strip()} is not in the cited Evidence."
        for amount in AMOUNT.findall(remainder)
        if _as_number(amount) not in numbers
    ]
    return errors


def complete_citations(draft: ReportDraft, evidence: list[Evidence]) -> ReportDraft:
    """Adds a citation when a value is in a record the model forgot to cite.

    A value found in no record still fails, so an invented fact can't pass.
    """
    by_id = {e.id: e for e in evidence}
    findings = []
    for finding in draft.findings:
        ids = list(finding.evidence_ids)
        cited = [by_id[i] for i in ids if i in by_id]
        for error in check_statement(finding.statement, cited):
            value = error.split(" is not in")[0].rsplit(" ", 1)[-1]
            holder = next((e for e in evidence if not check_statement(value, [e])), None)
            if holder and holder.id not in ids:
                ids.append(holder.id)
        findings.append(finding.model_copy(update={"evidence_ids": ids}))
    return draft.model_copy(update={"findings": findings})


def verify(draft: ReportDraft, evidence: list[Evidence]) -> list[str]:
    by_id = {e.id: e for e in evidence}
    errors: list[str] = []
    if draft.assessment == "suspicious" and "no_action" in draft.recommended_actions:
        errors.append("no_action cannot be recommended on a suspicious assessment.")
    if not draft.findings:
        errors.append("The report has no findings.")
    for n, finding in enumerate(draft.findings, start=1):
        if not finding.evidence_ids:
            errors.append(f"Finding {n} cites no Evidence.")
        unknown = [i for i in finding.evidence_ids if i not in by_id]
        errors += [f"Finding {n} cites unknown Evidence {i}." for i in unknown]
        cited = [by_id[i] for i in finding.evidence_ids if i in by_id]
        errors += [f"Finding {n}: {e}" for e in check_statement(finding.statement, cited)]
    return errors
