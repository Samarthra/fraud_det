"""Builds facts from a Case's records, proves Typologies and says what the Assessment must be."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from contracts import (
    Alert,
    OtpFact,
    TypologyNear,
    TypologyProof,
    TypologyResult,
    TypologyStep,
)
from correlation.consolidate import same_household, subject_record
from detection.engine import device_first_seen, load_config

from .engine import Fact, Rule, Source, evaluate, first_time, load_rules, nearest, proof_steps

NEEDS_NO_COVER = {"amount_spike", "off_hours"}
OUTSIDE = "a claim outside your Portfolio"


def seconds(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp())


def case_window(alerts: list[Alert], config: dict[str, Any]) -> tuple[int, int]:
    """Old fraud on an account says nothing about today's Case, so proofs stay in this window."""
    times = [datetime.fromisoformat(a.created_at) for a in alerts]
    lookback = timedelta(days=config["typology"]["lookback_days"])
    return int((min(times) - lookback).timestamp()), int(max(times).timestamp())


def events_to_read(records: dict[str, Any], config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Enrolments worth reading. One with a blocker can't prove, so its text is never sent."""
    config = config or load_config()
    start, end = case_window(records["alerts"], config)
    quiet = config["typology"]["quiet_hours"] * 3600
    out = []
    for event in records["events"]:
        if event["type"] != "device_enrolled" or not event.get("event_id"):
            continue
        at = seconds(event["at"])
        if not start <= at <= end:
            continue
        before = [e for e in records["events"]
                  if e["account_id"] == event["account_id"] and e["type"] in ("sim_swap", "password_reset")
                  and 0 <= at - seconds(e["at"]) <= quiet]
        failed = [l for l in records["logins"]
                  if l["account_id"] == event["account_id"] and l["outcome"] == "failure"
                  and 0 <= at - seconds(l["timestamp"]) <= quiet]
        if not before and not failed:
            out.append(event)
    return out


def _login_facts(records, failures: int, minutes: int) -> list[Fact]:
    facts = []
    by_account = defaultdict(list)
    for login in records["logins"]:
        by_account[login["account_id"]].append(login)
    for account_id, logins in by_account.items():
        recent: list[dict] = []
        for login in sorted(logins, key=lambda r: r["timestamp"]):
            when = seconds(login["timestamp"])
            source = Source("login", login["login_id"])
            if login["outcome"] == "failure":
                recent.append(login)
                facts.append(Fact("failed_login", (login["login_id"], account_id, when), source))
                continue
            near = [f for f in recent if when - seconds(f["timestamp"]) <= minutes * 60]
            if len(near) >= failures:
                facts.append(Fact("failed_then_success", (login["login_id"], account_id, len(near), when), source))
            recent = []
    return facts


def _payment_facts(records, new_device_hours: int, mule_days: int) -> list[Fact]:
    facts = []
    payers = records["beneficiary_payers"]
    seen = device_first_seen({"logins": records["logins"], "transactions": records["transactions"]})
    earliest: dict[str, Any] = {}
    for (account_id, _), when in seen.items():
        earliest[account_id] = min(when, earliest.get(account_id, when))
    paid: dict[str, set] = defaultdict(set)
    for t in sorted(records["transactions"], key=lambda r: r["timestamp"]):
        account_id, beneficiary = t["account_id"], t["beneficiary_id"]
        ref, when, device = t["transaction_id"], seconds(t["timestamp"]), t.get("device_id")
        source = Source("transaction", ref)
        facts.append(Fact("payment", (ref, account_id, beneficiary, t["amount"], device, when), source))
        if beneficiary not in paid[account_id]:
            facts.append(Fact("first_payment", (ref,), source))
        paid[account_id].add(beneficiary)
        first = seen.get((account_id, device))
        if first and first > earliest[account_id] and timedelta(0) <= datetime.fromisoformat(t["timestamp"]) - first <= timedelta(hours=new_device_hours):
            facts.append(Fact("new_device", (ref, device), source))
        rows = payers.get(beneficiary, [])
        count = len({a for at, a in rows if 0 <= when - seconds(at) <= mule_days * 86400})
        facts.append(Fact("payer_count", (ref, count), source))
        if {a for _, a in rows} == {account_id}:
            facts.append(Fact("only_payer", (account_id, beneficiary), source))
    return facts


def _claim_facts(records) -> list[Fact]:
    facts = []
    owners = records["customer_rows"]
    for claim in records["claims"]:
        account = records["claim_accounts"].get(claim["claim_id"])
        if account is None:
            continue
        claim_id, source = claim["claim_id"], Source("claim", claim["claim_id"])
        facts.append(Fact("claim", (claim_id, account, seconds(claim["timestamp"])), source))
        for other in records["claim_mates"]:
            if other["claim_id"] == claim_id or other["customer_id"] == claim["customer_id"]:
                continue
            one, two = owners.get(claim["customer_id"]), owners.get(other["customer_id"])
            if one and two and same_household(one, two):
                continue
            for key, label in (("device_id", "device"), ("ip", "IP"), ("phone", "phone")):
                if claim.get(key) and claim[key] == other.get(key):
                    mine = other["claim_id"] in records["own_claims"]
                    facts.append(Fact(
                        "shared_claim",
                        (claim_id, other["claim_id"] if mine else OUTSIDE, label, claim[key], seconds(other["timestamp"])),
                        Source("claim", other["claim_id"]) if mine else None,
                    ))
    return facts


def build_facts(records: dict[str, Any], otp: list[OtpFact], config: dict[str, Any]) -> list[Fact]:
    rules = config["rules"]
    logins = rules["login_failures_then_success"]
    facts = _login_facts(records, logins["failures"], logins["within_minutes"])
    facts += _payment_facts(records, rules["new_device"]["hours"], rules["mule_beneficiary"]["window_days"])
    facts += _claim_facts(records)
    for event in records["events"]:
        source = Source("account_event", event.get("event_id") or f"{event['account_id']}/{event['type']}/{event['at']}")
        facts.append(Fact("event", (source.ref, event["account_id"], event["type"], event.get("target_id"), seconds(event["at"])), source))
    for loan in records["loans"]:
        if loan.get("disbursed_account_id") and loan.get("disbursed_at"):
            facts.append(Fact("payout", (loan["application_id"], loan["disbursed_account_id"], loan["amount"], seconds(loan["disbursed_at"])),
                              Source("loan_application", loan["application_id"])))
    facts += [Fact("otp_verified", (f.event_id, f.quote), Source("account_event", f.event_id)) for f in otp]
    return facts


def _covered(alert: Alert, proofs: list[TypologyProof]) -> bool:
    here = [p for p in proofs if p.account == alert.account_id]
    for hit in alert.rule_hits:
        if hit.rule in NEEDS_NO_COVER:
            continue
        if hit.rule == "new_device" and any(
            p.typology == "verified_device_change" and p.subject == alert.device_id
            and p.at is not None and p.at <= seconds(alert.created_at)  # verifying later clears nothing
            for p in here
        ):
            continue
        beneficiary = subject_record(alert).get("beneficiary_id")
        if hit.rule == "new_beneficiary" and any(p.typology == "established_payee" and p.subject == beneficiary for p in here):
            continue
        return False
    return True


def requirement(alerts: list[Alert], proofs: list[TypologyProof]) -> str:
    if any(p.direction == "fraud" for p in proofs):
        return "suspicious"
    if proofs and all(_covered(a, proofs) for a in alerts):
        return "not_suspicious"
    return "none"


def prove(records: dict[str, Any], otp: list[OtpFact], rules: list[Rule] | None = None) -> tuple[TypologyResult, list[Source]]:
    """Returns the result, and every record the proofs cite."""
    rules = rules or load_rules()
    config = load_config()
    window = case_window(records["alerts"], config)
    derived, index = evaluate(rules, build_facts(records, otp, config), window)
    proofs, cited = [], []
    for fact in derived:
        rule = fact.rule
        if not rule.typology:
            continue
        lines, sources = proof_steps(fact)
        steps = [TypologyStep(**s) for s in lines]
        proofs.append(TypologyProof(typology=rule.id, name=rule.name, direction=rule.typology,
                                    account=fact.args[0], subject=str(fact.args[1]),
                                    at=first_time(fact), steps=steps))
        cited += sources
    proved = {(p.typology, p.account) for p in proofs}
    accounts = sorted({a.account_id for a in records["alerts"]})
    near = [
        TypologyNear(typology=rule.id, name=rule.name, account=account, missing=missing)
        for rule in rules if rule.typology and rule.report_near
        for account, missing in nearest(rule, index, window, accounts).items()
        if (rule.id, account) not in proved
    ]
    result = TypologyResult(requirement=requirement(records["alerts"], proofs), proofs=proofs, near=near)
    return result, list(dict.fromkeys(cited))
