"""Groups Alerts into one Case. Only a matching identifier can link two Alerts, never a model."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from contracts import Alert, CaseLink, LinkReason


LINK_ORDER = ("account", "customer", "device", "beneficiary", "phone", "ip")  # strongest first
OWNER_KINDS = {"account", "customer"}
SUBJECT_KINDS = {"transaction", "login", "claim", "loan_application"}
Key = tuple[str, str]


@dataclass
class Group:
    alerts: list[Alert]
    reasons: list[LinkReason]


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _surname(name: str | None) -> str:
    return (name or "").strip().split(" ")[-1].lower()


def same_household(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return _surname(first["name"]) == _surname(second["name"]) and first["address"] == second["address"]


def inr(amount: float) -> str:
    """Indian digit grouping, matching the UI: ₹18,00,000."""
    whole = f"{amount:.0f}"
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return "₹" + ",".join(filter(None, [head, *groups, tail]))


def subject_record(alert: Alert) -> dict[str, Any]:
    """The Alert's own record. A loan Alert also carries its neighbours' applications."""
    own = {alert.transaction_id, alert.application_id, alert.claim_id} - {None}
    for record in alert.supporting_records:
        if record.source_ref in own or (not own and record.kind in SUBJECT_KINDS):
            return record.data
    return {}


def identifiers(alert: Alert, accounts: dict[str, dict[str, Any]]) -> set[Key]:
    record = subject_record(alert)
    phone = record.get("phone") or (accounts.get(alert.account_id) or {}).get("phone")
    found = {
        ("account", alert.account_id),
        ("customer", alert.customer_id),
        ("device", alert.device_id or record.get("device_id")),
        ("beneficiary", record.get("beneficiary_id")),
        ("ip", record.get("ip")),
        ("phone", phone),
    }
    return {(kind, value) for kind, value in found if value}


def _age(first: Alert, second: Alert) -> timedelta:
    return abs(datetime.fromisoformat(first.created_at) - datetime.fromisoformat(second.created_at))


def _linkable(kind: str, first: Alert, second: Alert, accounts, settings: dict[str, Any]) -> bool:
    if kind in OWNER_KINDS or first.customer_id == second.customer_id:
        # Sharing an owner is common, and so is using your own phone. Both Alerts must matter on
        # their own and fall close together, or everyday Low Alerts would pile into a Case.
        close = _age(first, second) <= timedelta(days=settings["owner_window_days"])
        return close and bool(first.case_id and second.case_id)
    if _age(first, second) > timedelta(days=settings["window_days"]):
        return False
    if kind == "beneficiary":
        # An ordinary shop is paid by everyone. Only a flagged mule proves a connection.
        return any(h.rule == "mule_beneficiary" for a in (first, second) for h in a.rule_hits)
    one, other = accounts.get(first.account_id), accounts.get(second.account_id)
    return not (one and other and same_household(one, other))  # a family sharing a phone


def explain(kind: str, value: str, alert_ids: list[str]) -> str:
    alerts = ", ".join(alert_ids)
    if kind in OWNER_KINDS:
        return f"{alerts} are on the same {kind}, {value}, within the correlation window."
    if kind == "beneficiary":
        return f"{alerts} all pay {value}, which detection flagged as a likely mule."
    name = "IP" if kind == "ip" else kind
    return f"{alerts} all name {name} {value} within the correlation window."


def find_groups(alerts: list[Alert], accounts: dict[str, dict[str, Any]], config: dict[str, Any]) -> list[Group]:
    settings = config["correlation"]
    by_key: dict[Key, list[Alert]] = defaultdict(list)
    for alert in sorted(alerts, key=lambda a: (a.created_at, a.id)):
        for key in identifiers(alert, accounts):
            by_key[key].append(alert)

    parent = {a.id: a.id for a in alerts}
    size = {a.id: 1 for a in alerts}

    def root(alert_id: str) -> str:
        while parent[alert_id] != alert_id:
            parent[alert_id] = parent[parent[alert_id]]
            alert_id = parent[alert_id]
        return alert_id

    matched: dict[Key, set[str]] = defaultdict(set)
    for kind in LINK_ORDER:
        for key in sorted(k for k in by_key if k[0] == kind):
            members = by_key[key]
            if kind not in OWNER_KINDS and len(members) > settings["hub_limit"]:
                continue
            for first, second in zip(members, members[1:]):
                if not _linkable(kind, first, second, accounts, settings):
                    continue
                a, b = root(first.id), root(second.id)
                if a != b:
                    if size[a] + size[b] > settings["max_alerts"]:
                        continue
                    parent[b] = a
                    size[a] += size[b]
                matched[key] |= {first.id, second.id}

    groups: dict[str, list[Alert]] = defaultdict(list)
    for alert in alerts:
        groups[root(alert.id)].append(alert)
    result = []
    for members in groups.values():
        if len(members) < 2:
            continue
        ids = {a.id for a in members}
        reasons = [
            LinkReason(kind=kind, value=value, alert_ids=sorted(found),
                       explanation=explain(kind, value, sorted(found)))
            for (kind, value), found in sorted(matched.items())
            if found <= ids
        ]
        result.append(Group(alerts=members, reasons=reasons))
    return result


def consolidate(store, config: dict[str, Any]) -> int:
    """Moves linked Alerts into one lead Case and returns how many moved. Alerts never change."""
    accounts = store.account_rows()
    separated = store.separated_alert_ids()
    by_portfolio: dict[str, list[Alert]] = defaultdict(list)
    for alert in store.all_alerts():
        account = accounts.get(alert.account_id)
        if account and alert.id not in separated:
            by_portfolio[account["portfolio"]].append(alert)

    moved = 0
    for portfolio in sorted(by_portfolio):
        for group in find_groups(by_portfolio[portfolio], accounts, config):
            moved += _apply(store, group, portfolio)
    return moved


def _lead_case(store, group: Group, homes: dict[str, str | None], worked: set[str]) -> str | None:
    best: dict[str, Alert] = {}
    for alert in group.alerts:
        home = homes.get(alert.id)
        if home and (home not in best or alert.score > best[home].score):
            best[home] = alert

    def rank(case_id: str):
        lead = best[case_id]
        return (case_id not in worked, -lead.score, lead.transaction_id is None,
                int(case_id.rsplit("-", 1)[-1]))

    return min(best, key=rank) if best else None


def _apply(store, group: Group, portfolio: str) -> int:
    homes = store.memberships()
    worked = store.worked_case_ids()
    lead = _lead_case(store, group, homes, worked)
    if lead is None:
        return 0
    absorbed = {homes.get(a.id) for a in group.alerts} - {lead, None} - worked
    grouped = {a.id for a in group.alerts}
    # An absorbed Case brings everything it already held, so nothing is left stranded.
    moving = sorted(
        alert_id for alert_id, home in homes.items()
        if home in absorbed or (alert_id in grouped and home is None)
    )
    at = now()
    for alert_id in moving:
        reasons = [r for r in group.reasons if alert_id in r.alert_ids] or group.reasons
        store.add_case_link(CaseLink(alert_id=alert_id, case_id=lead, action="grouped", reasons=reasons,
                                     actor="correlation", at=at))
    if moving:
        store.audit("alerts_grouped", portfolio=portfolio, case_id=lead, alert_ids=moving,
                    identifiers=[f"{r.kind} {r.value}" for r in group.reasons])
    return len(moving)
