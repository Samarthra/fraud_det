"""Writes fixtures/investigation.json, so the UI can be built with no agent running.

Run from backend/app: python -m demo.make_fixture
"""

import json
from pathlib import Path

from contracts import (
    Alert,
    Case,
    CaseDetail,
    Decision,
    Evidence,
    Finding,
    FollowUp,
    Investigation,
    Report,
    RuleHit,
    Step,
    SupportingRecord,
)

OUT = Path(__file__).resolve().parents[3] / "fixtures" / "investigation.json"
INV = "INV-1"
PAYMENT = {
    "transaction_id": "TXN-50001",
    "account_id": "ACC-10042",
    "beneficiary_id": "BEN-7001",
    "beneficiary_name": "R K Traders",
    "amount": 185000.0,
    "timestamp": "2026-10-31T16:21:00+05:30",
    "channel": "mobile",
    "status": "completed",
    "device_id": "DEV-9001",
    "ip_country": "RO",
}


def at(minute: int, second: int = 0) -> str:
    return f"2026-10-31T16:{minute:02d}:{second:02d}+05:30"


def evidence(n: int, kind: str, ref: str, data: dict) -> Evidence:
    return Evidence(
        id=f"EV-{n}",
        investigation_id=INV,
        kind=kind,
        source_ref=ref,
        data=data,
        tool_call_id=f"call_{n}",
        collected_at=at(22, n),
    )


EVIDENCE = [
    evidence(1, "transaction", "TXN-50001", PAYMENT),
    evidence(
        2,
        "account",
        "ACC-10042",
        {"account_id": "ACC-10042", "opened_at": "2023-09-14", "median_outgoing_30d": 4200.0},
    ),
    evidence(
        3,
        "account_event",
        "ACC-10042/sim_swap",
        {"type": "sim_swap", "at": "2026-10-31T15:02:00+05:30", "details": "SIM replaced"},
    ),
    evidence(
        4,
        "account_event",
        "ACC-10042/password_reset",
        {"type": "password_reset", "at": "2026-10-31T15:06:00+05:30", "details": "Reset by SMS"},
    ),
    evidence(
        5,
        "device",
        "DEV-9001",
        {"device_id": "DEV-9001", "first_seen": "2026-10-31T15:09:00+05:30", "ip_country": "RO"},
    ),
    evidence(
        6,
        "relationship",
        "BEN-7001",
        {
            "beneficiary_id": "BEN-7001",
            "paying_accounts_7d": 6,
            "in_scope_accounts": ["ACC-10311", "ACC-10388", "ACC-10455"],
            "out_of_scope_count": 3,
            "derived_from": ["TXN-48810", "TXN-48972", "TXN-49120"],
        },
    ),
]

ALERT = Alert(
    id="ALT-12",
    case_id="CASE-12",
    category="account_takeover",
    product="core_banking",
    risk_level="high",
    score=100,
    rule_hits=[
        RuleHit(rule="login_failures_then_success", points=30, reason="4 failed logins, then a success"),
        RuleHit(rule="new_device", points=25, reason="DEV-9001 first seen under 24h ago"),
        RuleHit(rule="amount_spike", points=25, reason="₹1,85,000 is 44× the ₹4,200 median"),
        RuleHit(rule="new_beneficiary", points=20, reason="First payment to BEN-7001"),
        RuleHit(rule="mule_beneficiary", points=20, reason="6 accounts paid BEN-7001 in 7 days"),
        RuleHit(rule="foreign_ip", points=15, reason="IP country RO differs from IN"),
    ],
    customer_id="CUS-1042",
    account_id="ACC-10042",
    transaction_id="TXN-50001",
    device_id="DEV-9001",
    supporting_records=[
        SupportingRecord(kind="transaction", source_ref="TXN-50001", data=PAYMENT),
    ],
    created_at=at(21),
)

REPORT = Report(
    assessment="suspicious",
    summary="ACC-10042 shows the pattern of an account takeover ending in a large transfer to a likely mule.",
    findings=[
        Finding(
            statement="A SIM swap and password reset preceded the first use of DEV-9001.",
            evidence_ids=["EV-3", "EV-4", "EV-5"],
        ),
        Finding(
            statement="TXN-50001 sent 185000 to BEN-7001, against a 30-day median of 4200.",
            evidence_ids=["EV-1", "EV-2"],
        ),
        Finding(
            statement="6 accounts paid BEN-7001 in 7 days, which suggests a mule beneficiary.",
            evidence_ids=["EV-6"],
        ),
    ],
    limitations=["3 of the accounts paying BEN-7001 are outside this Analyst's Portfolio."],
    recommended_actions=["hold_transaction", "block_beneficiary", "contact_customer"],
    verification="verified",
)

STEPS = [
    ("triage", "stage_started", "Triage started", [], 22, 0),
    ("triage", "stage_finished", "Payment on ACC-10042 needs Evidence", [], 22, 1),
    ("evidence", "stage_started", "Gathering Evidence", [], 22, 1),
    ("evidence", "tool_call", "get_transactions(ACC-10042)", [], 22, 1),
    ("evidence", "tool_result", "Payment and account history", ["EV-1", "EV-2"], 22, 2),
    ("evidence", "tool_call", "get_account_events(ACC-10042)", [], 22, 2),
    ("evidence", "tool_result", "SIM swap and password reset found", ["EV-3", "EV-4"], 22, 3),
    ("evidence", "tool_call", "get_device(DEV-9001)", [], 22, 3),
    ("evidence", "tool_result", "Device first seen today", ["EV-5"], 22, 4),
    ("evidence", "tool_call", "analyze_relationships(BEN-7001)", [], 22, 4),
    ("evidence", "tool_result", "6 accounts paid this beneficiary", ["EV-6"], 22, 5),
    ("evidence", "stage_finished", "6 Evidence records gathered", [], 22, 5),
    ("synthesis", "stage_started", "Drafting the report", [], 22, 5),
    ("synthesis", "stage_finished", "Draft ready", [], 22, 7),
    ("verification", "verification", "All claims match their Evidence", [], 22, 7),
    ("report", "stage_finished", "Report saved", [], 22, 8),
]


def build() -> dict:
    case = Case(
        id="CASE-12",
        alert_id=ALERT.id,
        customer_id=ALERT.customer_id,
        account_id=ALERT.account_id,
        category=ALERT.category,
        risk_level=ALERT.risk_level,
        supporting_records=ALERT.supporting_records,
        status="report_ready",
        decisions=[
            Decision(
                decision="requires_investigation",
                analyst="analyst-1",
                note="High-risk transfer after a new device",
                at=at(21, 40),
            )
        ],
        investigation_id=INV,
    )
    investigation = Investigation(
        id=INV,
        case_id=case.id,
        status="complete",
        report=REPORT,
        evidence=EVIDENCE,
        follow_ups=[
            FollowUp(
                id="FUP-1",
                question="Which other accounts paid this beneficiary?",
                answer="ACC-10311, ACC-10388 and ACC-10455 paid BEN-7001. 3 more are outside your Portfolio.",
                evidence_ids=["EV-6"],
                verification="verified",
                asked_at=at(24),
            )
        ],
        trace_url="https://us.cloud.langfuse.com/project/example/traces/example",
    )
    steps = [
        Step(seq=i, stage=stage, type=kind, summary=text, evidence_ids=ids, at=at(minute, second))
        for i, (stage, kind, text, ids, minute, second) in enumerate(STEPS, start=1)
    ]
    return {
        "case": CaseDetail(case=case, alert=ALERT, report=REPORT).model_dump(mode="json"),
        "investigation": investigation.model_dump(mode="json"),
        "steps": [s.model_dump(mode="json") for s in steps],
    }


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {OUT}")
