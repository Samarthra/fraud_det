"""An in-memory AgentStore holding the two Investigation scenarios."""

from contracts import Alert, Evidence, FollowUp, RuleHit, Step, SupportingRecord


def alert(id, account, txn, device, category, score, hits):
    return Alert(
        id=id, case_id=f"CASE-{id}", category=category, product="core_banking",
        risk_level="high" if score >= 75 else "medium", score=score,
        rule_hits=[RuleHit(rule=r, points=p, reason=t) for r, p, t in hits],
        customer_id="CUS-1", account_id=account, transaction_id=txn, device_id=device,
        supporting_records=[], created_at="2026-10-31T16:21:00+05:30",
    )


TAKEOVER = alert("A1", "ACC-10042", "TXN-50001", "DEV-9001", "account_takeover", 100, [
    ("new_device", 25, "DEV-9001 first seen under 24h ago"),
    ("amount_spike", 25, "185000 is far above the median of 4200"),
    ("new_beneficiary", 20, "First payment to BEN-7001"),
    ("mule_beneficiary", 20, "6 accounts paid BEN-7001 in 7 days"),
    ("foreign_ip", 15, "IP country RO differs from IN"),
])
BENIGN = alert("A2", "ACC-20017", "TXN-50002", "DEV-9002", "suspicious_transfer", 70, [
    ("new_device", 25, "DEV-9002 first seen under 24h ago"),
    ("amount_spike", 25, "62000 is far above the median of 9000"),
    ("new_beneficiary", 20, "First payment to BEN-7002"),
])


class FakeStore:
    def __init__(self, alert=TAKEOVER):
        self.alert = alert
        self.steps: list[Step] = []
        self.evidence: list[Evidence] = []
        self.report = None
        self.trace_url = None
        self.audits: list[tuple[str, dict]] = []
        self.follow_ups: dict[str, FollowUp] = {}
        self.portfolios = {"ACC-10042": "p1", "ACC-20017": "p1", "ACC-10311": "p1",
                           "ACC-10388": "p1", "ACC-10455": "p1", "ACC-60001": "p2",
                           "ACC-60002": "p2", "ACC-60003": "p2"}
        self.accounts = {
            "ACC-10042": {"account_id": "ACC-10042", "opened_at": "2023-09-14", "median_outgoing_30d": 4200.0},
            "ACC-20017": {"account_id": "ACC-20017", "opened_at": "2021-06-02", "median_outgoing_30d": 9000.0},
        }
        self.transactions = {
            "ACC-10042": [
                {"transaction_id": "TXN-50001", "account_id": "ACC-10042", "beneficiary_id": "BEN-7001",
                 "beneficiary_name": "R K Traders", "amount": 185000.0, "timestamp": "2026-10-31T16:21:00+05:30",
                 "status": "completed", "device_id": "DEV-9001", "ip_country": "RO", "description": "Payment"},
                {"transaction_id": "TXN-48001", "account_id": "ACC-10042", "beneficiary_id": "BEN-1200",
                 "beneficiary_name": "Grocer", "amount": 4200.0, "timestamp": "2026-10-20T11:00:00+05:30",
                 "status": "completed", "device_id": "DEV-3001", "ip_country": "IN", "description": "Groceries"},
            ],
            "ACC-20017": [
                {"transaction_id": "TXN-50002", "account_id": "ACC-20017", "beneficiary_id": "BEN-7002",
                 "beneficiary_name": "S Mehta", "amount": 62000.0, "timestamp": "2026-10-31T13:00:00+05:30",
                 "status": "completed", "device_id": "DEV-9002", "ip_country": "IN", "description": "Rent deposit, new flat"},
                {"transaction_id": "TXN-47001", "account_id": "ACC-20017", "beneficiary_id": "BEN-1300",
                 "beneficiary_name": "Old landlord", "amount": 9000.0, "timestamp": "2026-10-01T09:00:00+05:30",
                 "status": "completed", "device_id": "DEV-3002", "ip_country": "IN", "description": "Rent"},
            ],
        }
        self.events = {
            "ACC-10042": [
                {"type": "failed_login", "at": "2026-10-31T14:55:00+05:30", "details": "4 failures, then success"},
                {"type": "sim_swap", "at": "2026-10-31T15:02:00+05:30", "details": "SIM replaced"},
                {"type": "password_reset", "at": "2026-10-31T15:06:00+05:30", "details": "Reset by SMS"},
                {"type": "device_enrolled", "at": "2026-10-31T15:09:00+05:30", "details": "DEV-9001, foreign IP RO"},
            ],
            "ACC-20017": [
                {"type": "device_enrolled", "at": "2026-10-31T10:00:00+05:30", "details": "DEV-9002 passed OTP to registered SIM, usual city Pune"},
                {"type": "beneficiary_added", "at": "2026-10-29T18:00:00+05:30", "details": "BEN-7002 added"},
            ],
        }
        self.devices = {
            "DEV-9001": {"device_id": "DEV-9001", "first_seen": "2026-10-31T15:09:00+05:30", "accounts": ["ACC-10042"]},
            "DEV-9002": {"device_id": "DEV-9002", "first_seen": "2026-10-31T10:00:00+05:30", "accounts": ["ACC-20017"]},
            "DEV-OUT": {"device_id": "DEV-OUT", "first_seen": "2026-10-01", "accounts": ["ACC-60001"]},
        }
        self.beneficiaries = {
            "BEN-7001": {"beneficiary_id": "BEN-7001", "name": "R K Traders", "first_paid": "2026-10-26"},
            "BEN-7002": {"beneficiary_id": "BEN-7002", "name": "S Mehta", "first_paid": "2026-10-31"},
            "BEN-OUT": {"beneficiary_id": "BEN-OUT", "name": "Other", "first_paid": "2026-10-01"},
        }
        self.payments = {
            "BEN-7001": [
                {"account_id": a, "transaction_id": f"TXN-{i}", "portfolio": self.portfolios[a]}
                for i, a in enumerate(["ACC-10042", "ACC-10311", "ACC-10388", "ACC-60001", "ACC-60002", "ACC-60003"], 48000)
            ],
            "BEN-7002": [{"account_id": "ACC-20017", "transaction_id": "TXN-50002", "portfolio": "p1"}],
            "BEN-OUT": [{"account_id": "ACC-60001", "transaction_id": "TXN-60000", "portfolio": "p2"}],
        }

    def get_alert_for_investigation(self, investigation_id): return self.alert
    def case_records(self, case_id, portfolio):
        return {"alerts": [self.alert], "logins": [], "events": [], "transactions": [], "beneficiary_payers": {},
                "loans": [], "claims": [], "claim_accounts": {}, "claim_mates": [], "own_claims": set(),
                "customer_rows": {}}

    def record_for(self, kind, ref): return {"ref": ref}
    def save_typology(self, investigation_id, result): self.typology = result
    def verification_attempts(self, investigation_id): return sum(s.type == "verification" for s in self.steps)
    def account_portfolio(self, account_id): return self.portfolios.get(account_id)
    def get_account(self, account_id): return self.accounts.get(account_id)
    def get_transactions(self, account_id, limit=10): return self.transactions.get(account_id, [])[:limit]
    def get_account_events(self, account_id, limit=10): return self.events.get(account_id, [])[:limit]
    def get_device(self, device_id): return self.devices.get(device_id)
    def get_beneficiary(self, beneficiary_id): return self.beneficiaries.get(beneficiary_id)
    def beneficiary_payments(self, beneficiary_id, days=7): return self.payments.get(beneficiary_id, [])
    def beneficiary_portfolios(self, beneficiary_id): return {p["portfolio"] for p in self.payments.get(beneficiary_id, [])}

    def append_step(self, investigation_id, stage, type, summary, evidence_ids=()):
        self.steps.append(Step(seq=len(self.steps) + 1, stage=stage, type=type, summary=summary,
                               evidence_ids=list(evidence_ids), at="2026-10-31T16:22:00+05:30"))

    def add_evidence(self, investigation_id, kind, source_ref, data, tool_call_id=None):
        for e in self.evidence:
            if e.kind == kind and e.source_ref == source_ref:
                return e
        row = Evidence(id=f"EV-{len(self.evidence) + 1}", investigation_id=investigation_id, kind=kind,
                       source_ref=source_ref, data=data, tool_call_id=tool_call_id,
                       collected_at="2026-10-31T16:22:00+05:30")
        self.evidence.append(row)
        return row

    def list_evidence(self, investigation_id): return list(self.evidence)
    def get_report(self, investigation_id): return self.report
    def save_report(self, investigation_id, report): self.report = report
    def set_trace_url(self, investigation_id, url): self.trace_url = url
    def get_follow_up(self, follow_up_id): return self.follow_ups[follow_up_id]
    def list_follow_ups(self, investigation_id): return list(self.follow_ups.values())

    def save_followup_answer(self, follow_up_id, answer, evidence_ids, verification):
        row = self.follow_ups[follow_up_id]
        row.answer, row.evidence_ids, row.verification = answer, list(evidence_ids), verification

    def audit(self, event, **details): self.audits.append((event, details))
