"""Rules add up to a 0-100 score. Everything configurable lives in rules.yaml."""

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

import yaml

from contracts import Alert, RiskLevel, RuleHit, SupportingRecord
from correlation.consolidate import consolidate, same_household

RULES_FILE = Path(__file__).with_name("rules.yaml")
IST = timezone(timedelta(hours=5, minutes=30))


def load_config(path: Path = RULES_FILE) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


@dataclass
class Candidate:
    dedupe_key: str
    subject_id: str
    category: str
    product: str
    customer_id: str
    account_id: str
    hits: list[RuleHit]
    records: list[SupportingRecord]
    at: str
    transaction_id: str | None = None
    device_id: str | None = None
    application_id: str | None = None
    policy_id: str | None = None
    claim_id: str | None = None
    score: int = field(init=False)

    def __post_init__(self):
        self.score = min(100, sum(h.points for h in self.hits))


def risk_level(score: int, config: dict[str, Any]) -> RiskLevel:
    thresholds = config["thresholds"]
    if score >= thresholds["high"]:
        return "high"
    return "medium" if score >= thresholds["actionable"] else "low"


def ts(row: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(row["timestamp"])


def hit(rule: str, points: int, reason: str) -> RuleHit:
    return RuleHit(rule=rule, points=points, reason=reason)


def scan(data: dict[str, list[dict[str, Any]]], config: dict[str, Any]) -> list[Candidate]:
    data = {**data, **{k: sorted(data[k], key=ts) for k in ("transactions", "logins", "loans")}}
    data = {"events": [], "policies": [], "claims": [], **data}
    accounts = {a["account_id"]: a for a in data["accounts"]}
    logins_by_account: dict[str, list] = defaultdict(list)
    for login in data["logins"]:
        logins_by_account[login["account_id"]].append(login)
    takeovers = _login_patterns(logins_by_account, config)
    first_seen = _device_first_seen(data)
    candidates = _transactions(data, accounts, first_seen, takeovers, config)
    candidates += _standalone_logins(accounts, first_seen, takeovers, config)
    candidates += _shared_devices(data, accounts, config)
    candidates += _loans(data, accounts, config)
    candidates += _claims(data, accounts, config)
    minimum = config["thresholds"]["record"]
    return [c for c in candidates if c.score >= minimum]


def _device_first_seen(data) -> dict[tuple[str, str], datetime]:
    seen: dict[tuple[str, str], datetime] = {}
    for row in [*data["logins"], *data["transactions"]]:
        if row.get("device_id"):
            key = (row["account_id"], row["device_id"])
            when = ts(row)
            if key not in seen or when < seen[key]:
                seen[key] = when
    return seen


def _login_patterns(logins_by_account, config) -> dict[str, list[dict[str, Any]]]:
    rule = config["rules"]["login_failures_then_success"]
    window = timedelta(minutes=rule["within_minutes"])
    patterns: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for account_id, logins in logins_by_account.items():
        failures: list[datetime] = []
        for login in logins:
            when = ts(login)
            if login["outcome"] == "failure":
                failures.append(when)
                continue
            recent = [f for f in failures if when - f <= window]
            if len(recent) >= rule["failures"]:
                patterns[account_id].append({"login": login, "failures": len(recent), "at": when})
            failures = []
    return patterns


def _transactions(data, accounts, first_seen, takeovers, config) -> list[Candidate]:
    rules = config["rules"]
    by_account: dict[str, list] = defaultdict(list)
    payers: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for t in data["transactions"]:
        by_account[t["account_id"]].append(t)
        payers[t["beneficiary_id"]].append((ts(t), t["account_id"]))

    payouts = _disbursements(data, config)
    candidates = []
    for account_id, transactions in by_account.items():
        account = accounts.get(account_id)
        if account is None:
            continue
        paid: set[str] = set()
        history: list[tuple[datetime, float]] = []
        times: list[datetime] = []
        for t in transactions:
            when = ts(t)
            hits = _transaction_hits(
                t, when, paid, history, times, payers, first_seen,
                takeovers.get(account_id, []), rules,
            )
            if history:
                hits += _proceeds_hits(t, when, paid, payouts.get(account_id, []), rules)
            paid.add(t["beneficiary_id"])
            history.append((when, t["amount"]))
            times.append(when)
            if hits:
                rules_hit = {h.rule for h in hits}
                if "loan_proceeds_transfer" in rules_hit:
                    category = "loan_proceeds_diversion"
                elif {"login_failures_then_success", "new_device"} & rules_hit:
                    category = "account_takeover"
                else:
                    category = "suspicious_transfer"
                candidates.append(
                    Candidate(
                        dedupe_key=f"transaction:{t['transaction_id']}",
                        subject_id=t["transaction_id"],
                        category=category,
                        product="core_banking",
                        customer_id=account["customer_id"],
                        account_id=account_id,
                        hits=hits,
                        records=[SupportingRecord(kind="transaction", source_ref=t["transaction_id"], data=t)],
                        at=t["timestamp"],
                        transaction_id=t["transaction_id"],
                        device_id=t.get("device_id"),
                    )
                )
    return candidates


def _transaction_hits(t, when, paid, history, times, payers, first_seen, patterns, rules):
    hits: list[RuleHit] = []
    has_history = bool(history)

    rule = rules["new_device"]
    device = t.get("device_id")
    seen = first_seen.get((t["account_id"], device)) if device else None
    earliest = min((w for (a, _), w in first_seen.items() if a == t["account_id"]), default=None) if seen else None
    if seen and earliest and seen > earliest and when - seen <= timedelta(hours=rule["hours"]):
        hits.append(hit("new_device", rule["points"], f"{device} first seen on this account under {rule['hours']}h ago"))

    rule = rules["amount_spike"]
    recent = [a for w, a in history if when - w <= timedelta(days=rule["window_days"])]
    if len(recent) >= rule["min_history"]:
        typical = median(recent)
        similar = sum(a >= 0.8 * t["amount"] for a in recent)
        if t["amount"] > rule["multiplier"] * typical and similar < 2:
            hits.append(hit("amount_spike", rule["points"], f"{t['amount']:.0f} is over {rule['multiplier']}× the median of {typical:.0f}"))

    rule = rules["new_beneficiary"]
    if has_history and t["beneficiary_id"] not in paid:
        hits.append(hit("new_beneficiary", rule["points"], f"First payment to {t['beneficiary_id']}"))

    rule = rules["mule_beneficiary"]
    window = timedelta(days=rule["window_days"])
    count = len({a for w, a in payers[t["beneficiary_id"]] if timedelta(0) <= when - w <= window})
    if count >= rule["accounts"]:
        hits.append(hit("mule_beneficiary", rule["points"], f"{count} accounts paid {t['beneficiary_id']} in {rule['window_days']} days"))

    rule = rules["velocity"]
    start = bisect_left(times, when - timedelta(minutes=rule["minutes"]))
    if len(times) - start + 1 >= rule["payments"]:
        hits.append(hit("velocity", rule["points"], f"{len(times) - start + 1} payments in {rule['minutes']} minutes"))

    rule = rules["foreign_ip"]
    country = t.get("ip_country")
    if country and country != rule["home_country"]:
        hits.append(hit("foreign_ip", rule["points"], f"IP country {country} differs from {rule['home_country']}"))

    rule = rules["off_hours"]
    hour = when.astimezone(IST).hour
    if rule["start_hour"] <= hour < rule["end_hour"]:
        hits.append(hit("off_hours", rule["points"], f"Made at {hour:02d}:00 IST"))

    rule = rules["login_failures_then_success"]
    for pattern in patterns:
        if timedelta(0) <= when - pattern["at"] <= timedelta(minutes=rule["transfer_within_minutes"]):
            hits.append(hit("login_failures_then_success", rule["points"], f"{pattern['failures']} failed logins, then a success, before this payment"))
            break
    return hits


def _disbursements(data, config) -> dict[str, list[dict[str, Any]]]:
    """Each paid-out loan by receiving account, and any bank change made shortly before it."""
    window = timedelta(days=config["rules"]["recent_bank_change"]["days"])
    changes: dict[str, list[datetime]] = defaultdict(list)
    for event in data["events"]:
        if event["type"] == "bank_account_changed":
            changes[event["account_id"]].append(datetime.fromisoformat(event["at"]))
    payouts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for loan in data["loans"]:
        account_id, paid_at = loan.get("disbursed_account_id"), loan.get("disbursed_at")
        if account_id and paid_at:
            at = datetime.fromisoformat(paid_at)
            changed = [c for c in changes[account_id] if timedelta(0) <= at - c <= window]
            payouts[account_id].append({"loan": loan, "at": at, "changed": bool(changed)})
    return payouts


def _proceeds_hits(t, when, paid, payouts, rules) -> list[RuleHit]:
    if t["beneficiary_id"] in paid:
        return []
    rule = rules["loan_proceeds_transfer"]
    hits: list[RuleHit] = []
    for payout in payouts:
        loan = payout["loan"]
        soon = timedelta(0) <= when - payout["at"] <= timedelta(hours=rule["hours"])
        if soon and t["amount"] >= rule["min_share"] * loan["amount"]:
            hits.append(hit("loan_proceeds_transfer", rule["points"],
                            f"{t['amount']:.0f} sent to a new beneficiary within {rule['hours']}h of {loan['application_id']} paying out {loan['amount']:.0f}"))
            if payout["changed"]:
                bank = rules["recent_bank_change"]
                hits.append(hit("recent_bank_change", bank["points"],
                                f"Bank details on {t['account_id']} changed within {bank['days']} days before the payout"))
            break
    return hits


def _standalone_logins(accounts, first_seen, takeovers, config) -> list[Candidate]:
    rules = config["rules"]
    candidates = []
    for account_id, patterns in takeovers.items():
        account = accounts.get(account_id)
        if account is None:
            continue
        for pattern in patterns:
            login = pattern["login"]
            rule = rules["login_failures_then_success"]
            hits = [hit("login_failures_then_success", rule["points"], f"{pattern['failures']} failed logins, then a success")]
            seen = first_seen.get((account_id, login["device_id"]))
            devices = [w for (a, _), w in first_seen.items() if a == account_id]
            if seen and seen > min(devices) and pattern["at"] - seen <= timedelta(hours=rules["new_device"]["hours"]):
                hits.append(hit("new_device", rules["new_device"]["points"], f"Success came from new device {login['device_id']}"))
            candidates.append(
                Candidate(
                    dedupe_key=f"login:{login['login_id']}",
                    subject_id=account_id,
                    category="repeated_login_failures",
                    product="core_banking",
                    customer_id=account["customer_id"],
                    account_id=account_id,
                    hits=hits,
                    records=[SupportingRecord(kind="login", source_ref=login["login_id"], data=login)],
                    at=login["timestamp"],
                    device_id=login["device_id"],
                )
            )
    return candidates




def _shared_devices(data, accounts, config) -> list[Candidate]:
    rule = config["rules"]["shared_device"]
    latest = max((ts(r) for r in [*data["logins"], *data["transactions"]]), default=None)
    if latest is None:
        return []
    since = latest - timedelta(days=rule["window_days"])
    by_device: dict[str, set[str]] = defaultdict(set)
    last_seen: dict[str, str] = {}
    for row in [*data["logins"], *data["transactions"]]:
        if row.get("device_id") and ts(row) >= since and row["account_id"] in accounts:
            by_device[row["device_id"]].add(row["account_id"])
            last_seen[row["device_id"]] = row["timestamp"]

    candidates = []
    for device_id, account_ids in by_device.items():
        members = [accounts[a] for a in sorted(account_ids)]
        customers = {m["customer_id"] for m in members}
        if len(customers) < rule["customers"]:
            continue
        family = all(same_household(members[0], m) for m in members)
        points = rule["family_points"] if family else rule["points"]
        reason = (
            f"{len(customers)} customers on {device_id}, all with one surname and address"
            if family
            else f"{len(customers)} unrelated customers on {device_id}"
        )
        candidates.append(
            Candidate(
                dedupe_key=f"device:{device_id}",
                subject_id=device_id,
                category="shared_device",
                product="core_banking",
                customer_id=members[0]["customer_id"],
                account_id=members[0]["account_id"],
                hits=[hit("shared_device", points, reason)],
                records=[
                    SupportingRecord(kind="account", source_ref=m["account_id"], data=m)
                    for m in members
                ],
                at=last_seen[device_id],
                device_id=device_id,
            )
        )
    return candidates


def _loans(data, accounts, config) -> list[Candidate]:
    rule = config["rules"]["multi_applicant_device"]
    by_customer = {}
    for account in data["accounts"]:
        by_customer.setdefault(account["customer_id"], account)
    window = timedelta(days=rule["window_days"])
    bank = config["rules"]["recent_bank_change"]
    changed = {
        p["loan"]["application_id"]
        for payouts in _disbursements(data, config).values()
        for p in payouts
        if p["changed"]
    }
    by_device: dict[str, list] = defaultdict(list)
    for loan in data["loans"]:
        by_device[loan["device_id"]].append(loan)

    candidates = []
    for device_id, loans in by_device.items():
        for loan in loans:
            nearby = [o for o in loans if abs(ts(o) - ts(loan)) <= window]
            customers = {o["customer_id"] for o in nearby}
            account = by_customer.get(loan["customer_id"])
            if account is None:
                continue
            hits = []
            if len(customers) >= rule["customers"]:
                hits.append(hit("multi_applicant_device", rule["points"], f"{len(customers)} customers applied from {device_id} within {rule['window_days']} days"))
            if loan["application_id"] in changed:
                hits.append(hit("recent_bank_change", bank["points"], f"Bank details changed within {bank['days']} days before {loan['application_id']} paid out"))
            if not hits:
                continue
            candidates.append(
                Candidate(
                    dedupe_key=f"loan:{loan['application_id']}",
                    subject_id=loan["application_id"],
                    category="suspicious_loan_application",
                    product="lending",
                    customer_id=loan["customer_id"],
                    account_id=account["account_id"],
                    hits=hits,
                    records=[
                        SupportingRecord(kind="loan_application", source_ref=o["application_id"], data=o)
                        for o in nearby
                    ],
                    at=loan["timestamp"],
                    device_id=device_id,
                    application_id=loan["application_id"],
                )
            )
    return candidates


def _identity_users(data, accounts) -> dict[tuple[str, str], set[str]]:
    """Which customers appear on each device, IP and phone, from every source system."""
    users: dict[tuple[str, str], set[str]] = defaultdict(set)
    for account in data["accounts"]:
        if account.get("phone"):
            users["phone", account["phone"]].add(account["customer_id"])
    for login in data["logins"]:
        users["device", login["device_id"]].add(login["customer_id"])
        if login.get("ip"):
            users["ip", login["ip"]].add(login["customer_id"])
    for t in data["transactions"]:
        if t.get("device_id") and t["account_id"] in accounts:
            users["device", t["device_id"]].add(accounts[t["account_id"]]["customer_id"])
    for row in [*data["loans"], *data["claims"]]:
        for key, kind in (("device_id", "device"), ("ip", "ip"), ("phone", "phone")):
            if row.get(key):
                users[kind, row[key]].add(row["customer_id"])
    return users


def _claims(data, accounts, config) -> list[Candidate]:
    early = config["rules"]["early_claim"]
    linked = config["rules"]["claim_linked_identity"]
    by_customer: dict[str, dict[str, Any]] = {}
    for account in data["accounts"]:
        by_customer.setdefault(account["customer_id"], account)
    policies = {p["policy_id"]: p for p in data["policies"]}
    users = _identity_users(data, accounts)

    candidates = []
    for claim in data["claims"]:
        account = by_customer.get(claim["customer_id"])
        if account is None:
            continue
        hits, records = [], [SupportingRecord(kind="claim", source_ref=claim["claim_id"], data=claim)]
        policy = policies.get(claim["policy_id"])
        if policy:
            records.append(SupportingRecord(kind="policy", source_ref=policy["policy_id"], data=policy))
            age = ts(claim) - datetime.fromisoformat(policy["start_date"])
            if timedelta(0) <= age <= timedelta(days=early["days"]):
                hits.append(hit("early_claim", early["points"], f"Claimed {age.days} days after {policy['policy_id']} began"))
        for key, kind in (("device_id", "device"), ("ip", "ip"), ("phone", "phone")):
            value = claim.get(key)
            others = {
                c for c in users.get((kind, value), set()) - {claim["customer_id"]}
                if c in by_customer and not same_household(account, by_customer[c])
            }
            if value and others:
                hits.append(hit("claim_linked_identity", linked["points"], f"{kind} {value} on this claim is also used by {len(others)} other customer(s)"))
                break
        if hits:
            candidates.append(
                Candidate(
                    dedupe_key=f"claim:{claim['claim_id']}",
                    subject_id=claim["claim_id"],
                    category="suspicious_insurance_claim",
                    product="insurance",
                    customer_id=claim["customer_id"],
                    account_id=account["account_id"],
                    hits=hits,
                    records=records,
                    at=claim["timestamp"],
                    device_id=claim.get("device_id"),
                    policy_id=claim["policy_id"],
                    claim_id=claim["claim_id"],
                )
            )
    return candidates


def persist(store, candidates: list[Candidate], config: dict[str, Any]) -> int:
    """Adds Alerts and opens Cases. Returns how many are new. Nothing existing changes."""
    actionable = config["thresholds"]["actionable"]
    created = 0
    for c in sorted(candidates, key=lambda x: x.at):
        if store.has_alert(c.dedupe_key):
            continue
        alert = Alert(
            id=store.next_alert_id(),
            case_id=store.next_case_id() if c.score >= actionable else None,
            category=c.category,
            product=c.product,
            risk_level=risk_level(c.score, config),
            score=c.score,
            rule_hits=c.hits,
            customer_id=c.customer_id,
            account_id=c.account_id,
            transaction_id=c.transaction_id,
            device_id=c.device_id,
            application_id=c.application_id,
            policy_id=c.policy_id,
            claim_id=c.claim_id,
            supporting_records=c.records,
            created_at=c.at,
        )
        store.add_alert(c.dedupe_key, alert)
        created += 1
        if alert.case_id:
            store.add_case(alert)
    return created


def run_detection(store, config: dict[str, Any] | None = None) -> int:
    config = config or load_config()
    created = persist(store, scan(store.detection_inputs(), config), config)
    consolidate(store, config)
    return created
