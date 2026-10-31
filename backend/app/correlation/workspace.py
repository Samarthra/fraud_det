"""What an Analyst sees for a Case. Every row comes from a source record in their Portfolio."""

from datetime import datetime, timedelta
from typing import Any

from correlation.consolidate import explain, inr

from contracts import (
    Alert,
    Case,
    CaseGraph,
    CaseLink,
    GraphEdge,
    GraphNode,
    HistoryEntry,
    LinkReason,
    TimelineEvent,
)

LOOKBACK = timedelta(days=3)
MAX_TIMELINE = 80
MAX_NEIGHBOURS = 6


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value)


def timeline(store, alerts: list[Alert], portfolio: str) -> list[TimelineEvent]:
    accounts = sorted({a.account_id for a in alerts})
    customers = sorted({a.customer_id for a in alerts})
    devices = {a.device_id for a in alerts} - {None}
    start = min(_moment(a.created_at) for a in alerts) - LOOKBACK
    end = max(_moment(a.created_at) for a in alerts)
    rows: list[TimelineEvent] = []

    def add(at: str | None, system: str, kind: str, ref: str, summary: str, always: bool = False):
        if at and (always or start <= _moment(at) <= end):
            rows.append(TimelineEvent(at=at, system=system, kind=kind, source_ref=ref, summary=summary))

    for alert in alerts:
        add(alert.created_at, alert.product, "alert", alert.id,
            f"{alert.id} raised: {alert.category.replace('_', ' ')}, score {alert.score}", True)
        if alert.transaction_id:
            row = store.get_transaction(alert.transaction_id)
            if row:
                add(row["timestamp"], "core_banking", "transaction", row["transaction_id"],
                    f"{inr(row['amount'])} sent from {row['account_id']} to {row['beneficiary_id']}", True)
    for row in store.logins_for(accounts):
        if row["outcome"] == "failure" or row["device_id"] in devices:
            add(row["timestamp"], "core_banking", "login", row["login_id"],
                f"{row['outcome'].capitalize()} login on {row['account_id']} from {row['device_id']}, IP {row['ip']}")
    for row in store.events_for(accounts):
        add(row["at"], "core_banking", "account_event", row["event_id"] or row["type"],
            f"{row['type'].replace('_', ' ').capitalize()} on {row['account_id']}: {row['details']}")
    for row in store.loans_for(customers):
        add(row["timestamp"], "lending", "loan_application", row["application_id"],
            f"{row['customer_id']} applied for {inr(row['amount'])} from {row['device_id']}")
        add(row["disbursed_at"], "lending", "disbursement", row["application_id"],
            f"{row['application_id']} paid {inr(row['amount'])} into {row['disbursed_account_id']}")
    claimed = set()
    for row in store.claims_for(customers):
        claimed.add(row["policy_id"])
        add(row["timestamp"], "insurance", "claim", row["claim_id"],
            f"{row['customer_id']} claimed {inr(row['amount'])} on {row['policy_id']}")
    for row in store.policies_for(customers):
        add(row["start_date"], "insurance", "policy", row["policy_id"],
            f"{row['policy_id']} began for {row['customer_id']}, cover {inr(row['sum_assured'])}",
            row["policy_id"] in claimed)
    return sorted(rows, key=lambda r: _moment(r.at))[-MAX_TIMELINE:]


class _GraphBuilder:
    def __init__(self, store, portfolio: str):
        self.store = store
        self.portfolio = portfolio
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[tuple[str, str, str], GraphEdge] = {}
        self.outside: set[str] = set()

    def node(self, id: str | None, type: str, label: str | None = None) -> str | None:
        if id and id not in self.nodes:
            self.nodes[id] = GraphNode(id=id, type=type, label=label or id)
        return id

    def edge(self, source: str | None, target: str | None, label: str, evidence: str) -> None:
        if source and target:
            self.edges.setdefault((source, target, label),
                                  GraphEdge(source=source, target=target, label=label, evidence=evidence))

    def customer(self, customer_id: str | None) -> str | None:
        rows = self.store.customer_accounts(customer_id, self.portfolio) if customer_id else []
        if not rows:
            return None
        self.node(customer_id, "customer", rows[0]["name"])
        for row in rows:
            self.account_row(row)
        return customer_id

    def account_row(self, row: dict[str, Any]) -> None:
        self.node(row["account_id"], "account")
        self.node(row["customer_id"], "customer", row["name"])
        self.edge(row["customer_id"], row["account_id"], "holds", f"{row['account_id']}.customer_id")
        self.node(row["phone"], "phone")
        self.edge(row["customer_id"], row["phone"], "registered phone", f"{row['account_id']}.phone")

    def account(self, account_id: str | None) -> str | None:
        row = self.store.account_row(account_id) if account_id else None
        if row is None or row["portfolio"] != self.portfolio:
            return None
        self.account_row(row)
        return account_id

    def transaction(self, data: dict[str, Any]) -> None:
        ref = self.node(data["transaction_id"], "transaction", f"{inr(data['amount'])}")
        account = self.account(data["account_id"])
        self.edge(account, ref, "made", f"{ref}.account_id")
        self.node(data["beneficiary_id"], "beneficiary", data.get("beneficiary_name"))
        self.edge(ref, data["beneficiary_id"], "pays", f"{ref}.beneficiary_id")
        self.edge(ref, self.node(data.get("device_id"), "device"), "from device", f"{ref}.device_id")

    def login(self, data: dict[str, Any]) -> None:
        account, ref = self.account(data["account_id"]), data["login_id"]
        self.edge(account, self.node(data["device_id"], "device"), "signed in from", f"{ref}.device_id")
        self.edge(account, self.node(data.get("ip"), "ip"), "signed in from", f"{ref}.ip")

    def application(self, data: dict[str, Any]) -> None:
        ref = self.node(data["application_id"], "application", f"{inr(data['amount'])} loan")
        self.edge(self.customer(data["customer_id"]), ref, "applied", f"{ref}.customer_id")
        self._contact(ref, data, "submitted from")
        self.edge(ref, self.account(data.get("disbursed_account_id")), "paid into",
                  f"{ref}.disbursed_account_id")

    def claim(self, data: dict[str, Any]) -> None:
        ref = self.node(data["claim_id"], "claim", f"{inr(data['amount'])} claim")
        self.edge(self.customer(data["customer_id"]), ref, "claimed", f"{ref}.customer_id")
        self.edge(self.node(data["policy_id"], "policy"), ref, "paid under", f"{ref}.policy_id")
        self._contact(ref, data, "submitted from")

    def policy(self, data: dict[str, Any]) -> None:
        ref = self.node(data["policy_id"], "policy", data.get("product"))
        self.edge(self.customer(data["customer_id"]), ref, "insured by", f"{ref}.customer_id")

    def _contact(self, ref: str, data: dict[str, Any], label: str) -> None:
        for key, kind in (("device_id", "device"), ("ip", "ip"), ("phone", "phone")):
            self.edge(ref, self.node(data.get(key), kind), label, f"{ref}.{key}")

    def neighbours(self) -> None:
        """Who else shares a Case's device or mule. Other Portfolios stay a bare count."""
        for node in list(self.nodes.values()):
            if node.type == "device":
                device = self.store.get_device(node.id)
                others = device["accounts"] if device else []
                pairs = [(a, f"{node.id} seen on {a} in login or transaction records") for a in others]
            elif node.type == "beneficiary":
                payments = self.store.beneficiary_payments(node.id, days=7)
                pairs = [(p["account_id"], f"{p['transaction_id']}.beneficiary_id") for p in payments]
            else:
                continue
            shown = 0
            for account_id, evidence in pairs:
                if self.store.account_portfolio(account_id) != self.portfolio:
                    self.outside.add(account_id)
                elif account_id in self.nodes or shown < MAX_NEIGHBOURS:
                    shown += account_id not in self.nodes
                    self.edge(self.account(account_id), node.id, "shares", evidence)

    def build(self) -> CaseGraph:
        return CaseGraph(nodes=list(self.nodes.values()), edges=list(self.edges.values()),
                         out_of_scope_count=len(self.outside))


def case_graph(store, alerts: list[Alert], portfolio: str) -> CaseGraph:
    """`alerts` must already be scoped, so no record here comes from another Portfolio."""
    graph = _GraphBuilder(store, portfolio)
    readers = {"transaction": graph.transaction, "login": graph.login, "policy": graph.policy,
               "loan_application": graph.application, "claim": graph.claim}
    for alert in alerts:
        graph.customer(alert.customer_id)
        account = graph.account(alert.account_id)
        graph.edge(account, graph.node(alert.device_id, "device"), "alerted on", f"{alert.id}.device_id")
        for record in alert.supporting_records:
            if record.kind == "account":
                graph.edge(graph.account(record.source_ref), alert.device_id, "shares", f"{alert.id} supporting record")
            elif record.kind in readers:
                readers[record.kind](record.data)
    graph.neighbours()
    return graph.build()


def current_reasons(links: list[CaseLink], alert_ids: list[str]) -> list[LinkReason]:
    """Why the Alerts now in this Case belong together, leaving out anyone since separated."""
    inside = set(alert_ids)
    reasons: dict[tuple[str, str], LinkReason] = {}
    for link in links:
        if link.alert_id in inside:
            for reason in link.reasons:
                members = sorted(set(reason.alert_ids) & inside)
                if len(members) > 1:
                    reasons[reason.kind, reason.value] = reason.model_copy(update={
                        "alert_ids": members,
                        "explanation": explain(reason.kind, reason.value, members),
                    })
    return list(reasons.values())


def history(store, case: Case, alerts: list[Alert]) -> list[HistoryEntry]:
    rows: list[HistoryEntry] = []

    def add(at: str, event: str, actor: str, summary: str):
        rows.append(HistoryEntry(at=at, event=event, actor=actor, summary=summary))

    for alert in alerts:
        rules = ", ".join(h.rule for h in alert.rule_hits)
        add(alert.created_at, "alert_raised", "detection",
            f"{alert.id} classified {alert.risk_level} at score {alert.score}: {rules}")
    for link in store.case_links(case.id):
        text = f"{link.alert_id} {link.action}"
        if link.reasons:
            text += " on " + ", ".join(f"{r.kind} {r.value}" for r in link.reasons)
        if link.note:
            text += f". Reason: {link.note}"
        add(link.at, f"alert_{link.action}", link.actor, text)
    if case.investigation_id:
        steps = store.steps(case.investigation_id)
        report = store.get_report(case.investigation_id)
        if steps:
            add(steps[0].at, "investigation_started", "agent", f"Investigation {case.investigation_id} of {case.alert_id}")
        if steps and report:
            add(steps[-1].at, "assessment_saved", "agent",
                f"AI Assessment {report.assessment or 'none'}, {report.verification}")
    for item in store.classifications(case.id):
        add(item.at, "risk_reclassified", item.analyst,
            f"Risk changed from {item.previous} to {item.risk_level}. Reason: {item.reason}")
    for note in store.notes(case.id):
        add(note.at, "note_added", note.analyst, note.text)
    for item in case.decisions:
        target = f" to {item.escalate_to.replace('_', ' ')}" if item.escalate_to else ""
        add(item.at, "decision_recorded", item.analyst,
            f"{item.decision.replace('_', ' ').capitalize()}{target}" + (f". {item.note}" if item.note else ""))
    return sorted(rows, key=lambda r: _moment(r.at))
