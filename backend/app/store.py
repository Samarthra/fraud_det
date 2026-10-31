"""SQLite schema, writes and read-only query helpers. Implements agent.ports.AgentStore."""

import json
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from hmac import compare_digest
from statistics import median
from typing import Any, Sequence
from uuid import uuid4

from contracts import (
    Alert,
    Analyst,
    Case,
    CaseDetail,
    CaseLink,
    Classification,
    Decision,
    Evidence,
    FollowUp,
    Investigation,
    Note,
    Report,
    Stats,
    Step,
)
from correlation.priority import assess
from detection.engine import load_config

ANALYSTS = [
    Analyst(id="analyst-1", name="Asha Menon", portfolio="portfolio-1"),
    Analyst(id="analyst-2", name="Ravi Iyer", portfolio="portfolio-2"),
]
USER_CREDENTIALS = [
    {"username": "analyst-1", "password": "password", "analyst_id": "analyst-1"},
    {"username": "analyst-2", "password": "password", "analyst_id": "analyst-2"},
    {"username": "user1", "password": "password", "analyst_id": "analyst-1"},
    {"username": "user2", "password": "password", "analyst_id": "analyst-2"},
]

MAX_LINKED_ACCOUNTS = 12
FINAL_DECISIONS = {"false_positive", "confirmed_fraud", "escalated", "concluded"}
RECOMMENDATIONS = {"hold_recommended", "verification_recommended"}  # never change a Case's status
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
MAX_NODE_RECORDS = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (account_id TEXT PRIMARY KEY, customer_id TEXT, name TEXT,
  phone TEXT, email TEXT, address TEXT, onboarded_at TEXT, portfolio TEXT);
CREATE TABLE IF NOT EXISTS transactions (transaction_id TEXT PRIMARY KEY, account_id TEXT,
  beneficiary_id TEXT, beneficiary_name TEXT, amount REAL, timestamp TEXT, channel TEXT,
  status TEXT, device_id TEXT, ip_country TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS logins (login_id TEXT PRIMARY KEY, account_id TEXT, customer_id TEXT,
  device_id TEXT, ip TEXT, timestamp TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS loan_applications (application_id TEXT PRIMARY KEY, customer_id TEXT,
  device_id TEXT, amount REAL, status TEXT, timestamp TEXT, ip TEXT, phone TEXT,
  disbursed_account_id TEXT, disbursed_at TEXT);
CREATE TABLE IF NOT EXISTS account_events (account_id TEXT, type TEXT, at TEXT, details TEXT,
  event_id TEXT);
CREATE TABLE IF NOT EXISTS policies (policy_id TEXT PRIMARY KEY, customer_id TEXT, product TEXT,
  sum_assured REAL, start_date TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS claims (claim_id TEXT PRIMARY KEY, policy_id TEXT, customer_id TEXT,
  amount REAL, status TEXT, timestamp TEXT, device_id TEXT, ip TEXT, phone TEXT);
CREATE TABLE IF NOT EXISTS case_links (seq INTEGER PRIMARY KEY AUTOINCREMENT, alert_id TEXT,
  case_id TEXT, action TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS notes (case_id TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS classifications (case_id TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS ground_truth (subject_id TEXT PRIMARY KEY, is_fraud INTEGER, story TEXT);
CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, dedupe_key TEXT UNIQUE, account_id TEXT,
  body TEXT);
CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, account_id TEXT, alert_id TEXT,
  investigation_id TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS decisions (case_id TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS investigations (id TEXT PRIMARY KEY, case_id TEXT, status TEXT,
  report TEXT, trace_url TEXT, is_replay INTEGER DEFAULT 0, replay_captured_at TEXT);
CREATE TABLE IF NOT EXISTS evidence (id TEXT, investigation_id TEXT, kind TEXT, source_ref TEXT,
  body TEXT, PRIMARY KEY (investigation_id, kind, source_ref));
CREATE TABLE IF NOT EXISTS steps (investigation_id TEXT, seq INTEGER, body TEXT);
CREATE TABLE IF NOT EXISTS follow_ups (id TEXT PRIMARY KEY, investigation_id TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS baseline (dedupe_key TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, n INTEGER);
CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT, at TEXT,
  details TEXT);
"""
DATA_TABLES = (
    "accounts transactions logins loan_applications account_events ground_truth alerts cases "
    "decisions investigations evidence steps follow_ups counters baseline policies claims "
    "case_links notes classifications"
).split()
ADDED_COLUMNS = {
    "loan_applications": "ip phone disbursed_account_id disbursed_at".split(),
    "account_events": ["event_id"],
}
COLUMNS = {
    "customers": ("accounts", "account_id customer_id name phone email address onboarded_at portfolio"),
    "transactions": (
        "transactions",
        "transaction_id account_id beneficiary_id beneficiary_name amount timestamp channel status "
        "device_id ip_country description",
    ),
    "logins": ("logins", "login_id account_id customer_id device_id ip timestamp outcome"),
    "loan_applications": (
        "loan_applications",
        "application_id customer_id device_id amount status timestamp ip phone "
        "disbursed_account_id disbursed_at",
    ),
    "account_events": ("account_events", "event_id account_id type at details"),
    "policies": ("policies", "policy_id customer_id product sum_assured start_date status"),
    "claims": (
        "claims",
        "claim_id policy_id customer_id amount status timestamp device_id ip phone",
    ),
}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        # Demo data on one machine, so speed matters more than surviving a power cut.
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=OFF")
        self.db.executescript(SCHEMA)
        self._add_missing_columns()

    def _add_missing_columns(self) -> None:
        """A database from before Level 2 keeps working, and a reset fills the new columns."""
        for table, columns in ADDED_COLUMNS.items():
            present = {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}
            for column in columns:
                if column not in present:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        self.db.commit()

    def _all(self, sql: str, *args) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def _one(self, sql: str, *args) -> dict[str, Any] | None:
        rows = self._all(sql, *args)
        return rows[0] if rows else None

    def _run(self, sql: str, *args) -> None:
        with self.lock:
            self.db.execute(sql, args)
            self.db.commit()

    def _next_id(self, table: str, prefix: str) -> str:
        """IDs never repeat, even after a replaced Investigation is removed."""
        with self.lock:
            row = self._one("SELECT n FROM counters WHERE name=?", table)
            n = (row["n"] if row else 0) + 1
            self._run("INSERT OR REPLACE INTO counters VALUES (?,?)", table, n)
            return f"{prefix}-{n}"

    def reset(self) -> None:
        with self.lock:
            for table in DATA_TABLES:
                self.db.execute(f"DELETE FROM {table}")
            self.db.commit()

    # Analysts
    def analysts(self) -> list[Analyst]:
        return ANALYSTS

    def analyst(self, analyst_id: str | None) -> Analyst | None:
        return next((a for a in ANALYSTS if a.id == analyst_id), None)

    def users(self) -> list[dict[str, str]]:
        return [{"username": u["username"], "analyst_id": u["analyst_id"]} for u in USER_CREDENTIALS
                if u["username"] in {"analyst-1", "analyst-2", "user1", "user2"}]

    def authenticate(self, username: str, password: str) -> str | None:
        for u in USER_CREDENTIALS:
            same_user = compare_digest(u["username"].encode(), username.encode())
            if same_user and compare_digest(u["password"].encode(), password.encode()):
                return u["analyst_id"]
        return None

    # Loading data
    def insert_rows(self, dataset: str, rows: list[dict[str, Any]]) -> None:
        table, names = COLUMNS[dataset]
        columns = names.split()
        sql = (
            f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) "
            f"VALUES ({','.join('?' * len(columns))})"
        )
        with self.lock:
            self.db.executemany(sql, [[r.get(c) for c in columns] for r in rows])
            self.db.commit()

    def insert_ground_truth(self, rows: list[dict[str, Any]]) -> None:
        with self.lock:
            self.db.executemany(
                "INSERT OR REPLACE INTO ground_truth VALUES (?,?,?)",
                [(r["subject_id"], int(r["is_fraud"]), r["story"]) for r in rows],
            )
            self.db.commit()

    def ground_truth(self) -> list[dict[str, Any]]:
        """Only the eval runner calls this. No tool or route reads labels."""
        return self._all("SELECT * FROM ground_truth")

    def known_ids(self, portfolio: str | None = None) -> dict[str, set[str]]:
        def ids(sql: str) -> set[str]:
            return {next(iter(r.values())) for r in self._all(sql)}

        return {
            "account_id": ids("SELECT account_id FROM accounts"),
            "customer_id": ids("SELECT DISTINCT customer_id FROM accounts"),
            "transaction_id": ids("SELECT transaction_id FROM transactions"),
            "login_id": ids("SELECT login_id FROM logins"),
            "application_id": ids("SELECT application_id FROM loan_applications"),
            "event_id": ids("SELECT event_id FROM account_events WHERE event_id IS NOT NULL"),
            "policy_id": ids("SELECT policy_id FROM policies"),
            "claim_id": ids("SELECT claim_id FROM claims"),
            "own_account_id": {
                r["account_id"]
                for r in self._all("SELECT account_id FROM accounts WHERE portfolio=?", portfolio)
            },
            "own_customer_id": {
                r["customer_id"]
                for r in self._all("SELECT customer_id FROM accounts WHERE portfolio=?", portfolio)
            },
            "own_policy_id": {
                r["policy_id"]
                for r in self._all(
                    "SELECT policy_id FROM policies WHERE customer_id IN "
                    "(SELECT customer_id FROM accounts WHERE portfolio=?)",
                    portfolio,
                )
            },
        }

    def detection_inputs(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "accounts": self._all("SELECT * FROM accounts"),
            "transactions": self._all("SELECT * FROM transactions ORDER BY timestamp"),
            "logins": self._all("SELECT * FROM logins ORDER BY timestamp"),
            "loans": self._all("SELECT * FROM loan_applications ORDER BY timestamp"),
            "events": self._all("SELECT * FROM account_events"),
            "policies": self._all("SELECT * FROM policies"),
            "claims": self._all("SELECT * FROM claims ORDER BY timestamp"),
        }

    # Query helpers used by tools
    def relationship_graph(self, account_id: str, portfolio: str) -> dict[str, Any]:
        """One account's devices and beneficiaries, and who else in the Portfolio shares them."""
        payments = self._all(
            "SELECT DISTINCT beneficiary_id, beneficiary_name FROM transactions WHERE account_id=?",
            account_id,
        )
        devices = self._all(
            "SELECT device_id FROM transactions WHERE account_id=? AND device_id IS NOT NULL "
            "UNION SELECT device_id FROM logins WHERE account_id=?",
            account_id,
            account_id,
        )
        nodes = [{"id": account_id, "type": "account", "label": account_id}]
        edges = []
        hubs: dict[str, str] = {}
        for row in devices:
            hubs[row["device_id"]] = "device"
            nodes.append({"id": row["device_id"], "type": "device", "label": row["device_id"]})
            edges.append({"source": account_id, "target": row["device_id"], "label": "uses"})
        for row in payments:
            hubs[row["beneficiary_id"]] = "beneficiary"
            nodes.append({"id": row["beneficiary_id"], "type": "beneficiary", "label": row["beneficiary_name"]})
            edges.append({"source": account_id, "target": row["beneficiary_id"], "label": "pays"})

        shared: dict[str, set[str]] = {}
        for hub, kind in hubs.items():
            column = "device_id" if kind == "device" else "beneficiary_id"
            for row in self._all(f"SELECT DISTINCT account_id FROM transactions WHERE {column}=?", hub):
                shared.setdefault(row["account_id"], set()).add(hub)
            if kind == "device":
                for row in self._all("SELECT DISTINCT account_id FROM logins WHERE device_id=?", hub):
                    shared.setdefault(row["account_id"], set()).add(hub)
        shared.pop(account_id, None)

        visible = sorted(a for a in shared if self.account_portfolio(a) == portfolio)
        for other in visible[:MAX_LINKED_ACCOUNTS]:
            nodes.append({"id": other, "type": "account", "label": other})
            edges += [{"source": other, "target": hub, "label": "shares"} for hub in sorted(shared[other])]
        return {
            "nodes": nodes,
            "edges": edges,
            "more_in_portfolio": max(0, len(visible) - MAX_LINKED_ACCOUNTS),
            "out_of_scope_count": len(shared) - len(visible),
        }

    def graph_node_detail(self, node_id: str, kind: str, portfolio: str) -> dict[str, Any] | None:
        """Facts for one graph node. Returns None when the Analyst may not see it."""
        if kind == "account":
            account = self.get_account(node_id)
            if account is None or self.account_portfolio(node_id) != portfolio:
                return None
            alerts = [a for a in self.alerts(portfolio) if a.account_id == node_id]
            return {
                "id": node_id,
                "type": kind,
                "title": account["name"],
                "facts": [
                    {"label": "Customer", "value": account["customer_id"]},
                    {"label": "Onboarded", "value": account["onboarded_at"][:10]},
                    {"label": "Median payment", "value": f"₹{account['median_outgoing_30d'] or 0:,.0f}"},
                    {"label": "Alerts", "value": str(len(alerts))},
                ],
                "accounts": [],
                "out_of_scope_count": 0,
                "cases": [
                    {"id": a.case_id, "category": a.category, "risk_level": a.risk_level}
                    for a in alerts
                    if a.case_id
                ],
                "records": self._records(
                    "transaction", "transaction_id",
                    self.get_transactions(node_id, limit=MAX_NODE_RECORDS),
                ),
            }

        if kind in {"customer", "transaction", "application", "policy", "claim", "ip", "phone"}:
            return self._record_node(node_id, kind, portfolio)

        if kind == "device":
            device = self.get_device(node_id)
            accounts = device["accounts"] if device else []
            facts = [{"label": "First seen", "value": device["first_seen"][:10]}] if device else []
        elif kind == "beneficiary":
            beneficiary = self.get_beneficiary(node_id)
            if beneficiary is None or portfolio not in self.beneficiary_portfolios(node_id):
                return None
            rows = self._all(
                "SELECT DISTINCT account_id FROM transactions WHERE beneficiary_id=?", node_id
            )
            accounts = sorted(r["account_id"] for r in rows)
            facts = [
                {"label": "Name", "value": beneficiary["name"]},
                {"label": "First paid", "value": beneficiary["first_paid"][:10]},
                {"label": "Payments", "value": str(beneficiary["payment_count"])},
            ]
        else:
            return None
        visible = [a for a in accounts if self.account_portfolio(a) == portfolio]
        if not visible:
            return None
        return {
            "id": node_id,
            "type": kind,
            "title": node_id,
            "facts": facts,
            "accounts": visible,
            "out_of_scope_count": len(accounts) - len(visible),
            "cases": [],
            "records": self._linked_records(kind, node_id, portfolio),
        }

    @staticmethod
    def _records(kind: str, key: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"kind": kind, "source_ref": r[key], "data": r} for r in rows[:MAX_NODE_RECORDS]]

    def _own(self, rows: list[dict[str, Any]], portfolio: str) -> list[dict[str, Any]]:
        def allowed(row: dict[str, Any]) -> bool:
            if row.get("account_id"):
                return self.account_portfolio(row["account_id"]) == portfolio
            return portfolio in self.customer_portfolios(row["customer_id"])

        return [r for r in rows if allowed(r)]

    def _linked_records(self, kind: str, value: str, portfolio: str) -> list[dict[str, Any]]:
        """Records naming a device, IP, phone or beneficiary. Only this Portfolio's are returned."""
        records: list[dict[str, Any]] = []
        if kind == "beneficiary":
            rows = self._all("SELECT * FROM transactions WHERE beneficiary_id=?", value)
            return self._records("transaction", "transaction_id", self._own(rows, portfolio))
        column = {"device": "device_id", "ip": "ip", "phone": "phone"}[kind]
        sources = [("loan_application", "application_id", "loan_applications"),
                   ("claim", "claim_id", "claims")]
        if kind != "phone":
            sources.append(("login", "login_id", "logins"))
        if kind == "device":
            sources.append(("transaction", "transaction_id", "transactions"))
        for record_kind, key, table in sources:
            rows = self._all(f"SELECT * FROM {table} WHERE {column}=? ORDER BY timestamp DESC", value)
            records += self._records(record_kind, key, self._own(rows, portfolio))
        return records[:MAX_NODE_RECORDS]

    def _record_node(self, node_id: str, kind: str, portfolio: str) -> dict[str, Any] | None:
        """One customer, record, IP or phone. Returns None when nothing is in this Portfolio."""
        def node(title: str, facts: dict[str, Any], records: list[dict[str, Any]], accounts=()):
            return {
                "id": node_id, "type": kind, "title": title,
                "facts": [{"label": k, "value": str(v)} for k, v in facts.items() if v is not None],
                "accounts": list(accounts), "out_of_scope_count": 0, "cases": [], "records": records,
            }

        if kind == "customer":
            rows = self.customer_accounts(node_id, portfolio)
            if not rows:
                return None
            first = rows[0]
            return node(first["name"], {"Phone": first["phone"], "Email": first["email"],
                                        "Onboarded": first["onboarded_at"][:10]},
                        self._customer_records(node_id), [r["account_id"] for r in rows])
        if kind in {"ip", "phone"}:
            records = self._linked_records(kind, node_id, portfolio)
            if kind == "phone":
                rows = self._own(self._all("SELECT * FROM accounts WHERE phone=?", node_id), portfolio)
                accounts = [r["account_id"] for r in rows]
            else:
                accounts = sorted({r["data"]["account_id"] for r in records if r["data"].get("account_id")})
            if not records and not accounts:
                return None
            return node(node_id, {"Records": len(records)}, records, accounts)

        table, key, label = {
            "transaction": ("transactions", "transaction_id", "transaction"),
            "application": ("loan_applications", "application_id", "loan_application"),
            "policy": ("policies", "policy_id", "policy"),
            "claim": ("claims", "claim_id", "claim"),
        }[kind]
        rows = self._own(self._all(f"SELECT * FROM {table} WHERE {key}=?", node_id), portfolio)
        if not rows:
            return None
        row = rows[0]
        facts = {"Amount": row.get("amount"), "Status": row.get("status"), "Cover": row.get("sum_assured"),
                 "Product": row.get("product"), "Date": (row.get("timestamp") or row.get("start_date") or "")[:10]}
        return node(node_id, facts, self._records(label, key, rows))

    def _customer_records(self, customer_id: str) -> list[dict[str, Any]]:
        return (self._records("loan_application", "application_id", self.loans_for([customer_id]))
                + self._records("policy", "policy_id", self.policies_for([customer_id]))
                + self._records("claim", "claim_id", self.claims_for([customer_id])))[:MAX_NODE_RECORDS]

    def _rows_in(self, table: str, column: str, values: Sequence[str]) -> list[dict[str, Any]]:
        marks = ",".join("?" * len(values))
        return self._all(f"SELECT * FROM {table} WHERE {column} IN ({marks})", *values)

    def logins_for(self, account_ids: Sequence[str]) -> list[dict[str, Any]]:
        return self._rows_in("logins", "account_id", account_ids)

    def events_for(self, account_ids: Sequence[str]) -> list[dict[str, Any]]:
        return self._rows_in("account_events", "account_id", account_ids)

    def loans_for(self, customer_ids: Sequence[str]) -> list[dict[str, Any]]:
        return self._rows_in("loan_applications", "customer_id", customer_ids)

    def policies_for(self, customer_ids: Sequence[str]) -> list[dict[str, Any]]:
        return self._rows_in("policies", "customer_id", customer_ids)

    def claims_for(self, customer_ids: Sequence[str]) -> list[dict[str, Any]]:
        return self._rows_in("claims", "customer_id", customer_ids)

    def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM transactions WHERE transaction_id=?", transaction_id)

    def account_rows(self) -> dict[str, dict[str, Any]]:
        return {r["account_id"]: r for r in self._all("SELECT * FROM accounts")}

    def account_row(self, account_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM accounts WHERE account_id=?", account_id)

    def customer_accounts(self, customer_id: str, portfolio: str) -> list[dict[str, Any]]:
        return self._all(
            "SELECT * FROM accounts WHERE customer_id=? AND portfolio=? ORDER BY account_id",
            customer_id,
            portfolio,
        )

    def customer_portfolios(self, customer_id: str) -> set[str]:
        rows = self._all("SELECT portfolio FROM accounts WHERE customer_id=?", customer_id)
        return {r["portfolio"] for r in rows}

    def account_portfolio(self, account_id: str) -> str | None:
        row = self._one("SELECT portfolio FROM accounts WHERE account_id=?", account_id)
        return row["portfolio"] if row else None

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM accounts WHERE account_id=?", account_id)
        if row is None:
            return None
        amounts = [
            r["amount"]
            for r in self._all(
                "SELECT amount FROM transactions WHERE account_id=? ORDER BY timestamp DESC LIMIT 30",
                account_id,
            )
        ]
        return {
            "account_id": row["account_id"],
            "customer_id": row["customer_id"],
            "name": row["name"],
            "onboarded_at": row["onboarded_at"],
            "median_outgoing_30d": median(amounts) if amounts else None,
        }

    def get_transactions(self, account_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return self._all(
            "SELECT * FROM transactions WHERE account_id=? ORDER BY timestamp DESC LIMIT ?",
            account_id,
            limit,
        )

    def get_account_events(self, account_id: str, limit: int = 10) -> list[dict[str, Any]]:
        events = self._all(
            "SELECT account_id, type, at, details FROM account_events WHERE account_id=?", account_id
        )
        failures = self._all(
            "SELECT timestamp, device_id, ip FROM logins WHERE account_id=? AND outcome='failure'",
            account_id,
        )
        events += [
            {
                "account_id": account_id,
                "type": "failed_login",
                "at": f["timestamp"],
                "details": f"Failed login from {f['device_id']}, IP {f['ip']}",
            }
            for f in failures
        ]
        return sorted(events, key=lambda e: e["at"], reverse=True)[:limit]

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        rows = self._all(
            "SELECT account_id, timestamp FROM logins WHERE device_id=? "
            "UNION ALL SELECT account_id, timestamp FROM transactions WHERE device_id=?",
            device_id,
            device_id,
        )
        if not rows:
            return None
        return {
            "device_id": device_id,
            "first_seen": min(r["timestamp"] for r in rows),
            "accounts": sorted({r["account_id"] for r in rows}),
        }

    def get_beneficiary(self, beneficiary_id: str) -> dict[str, Any] | None:
        rows = self._all(
            "SELECT beneficiary_name, timestamp FROM transactions WHERE beneficiary_id=?",
            beneficiary_id,
        )
        if not rows:
            return None
        return {
            "beneficiary_id": beneficiary_id,
            "name": rows[0]["beneficiary_name"],
            "first_paid": min(r["timestamp"] for r in rows),
            "payment_count": len(rows),
        }

    def beneficiary_portfolios(self, beneficiary_id: str) -> set[str]:
        rows = self._all(
            "SELECT DISTINCT a.portfolio FROM transactions t JOIN accounts a USING (account_id) "
            "WHERE t.beneficiary_id=?",
            beneficiary_id,
        )
        return {r["portfolio"] for r in rows}

    def beneficiary_payments(self, beneficiary_id: str, days: int = 7) -> list[dict[str, Any]]:
        latest = self._one("SELECT MAX(timestamp) AS t FROM transactions")["t"]
        if latest is None:
            return []
        since = parse(latest) - timedelta(days=days)
        rows = self._all(
            "SELECT t.account_id, t.transaction_id, t.timestamp, a.portfolio FROM transactions t "
            "JOIN accounts a USING (account_id) WHERE t.beneficiary_id=?",
            beneficiary_id,
        )
        return [r for r in rows if parse(r["timestamp"]) >= since]

    # Alerts and Cases
    def has_alert(self, dedupe_key: str) -> bool:
        return (
            self._one("SELECT id FROM alerts WHERE dedupe_key=?", dedupe_key) is not None
            or self._one("SELECT 1 AS x FROM baseline WHERE dedupe_key=?", dedupe_key) is not None
        )

    def add_baseline(self, dedupe_keys: list[str]) -> None:
        """History left out of the sample backlog, so later scans don't flood the queue."""
        with self.lock:
            self.db.executemany(
                "INSERT OR IGNORE INTO baseline VALUES (?)", [(k,) for k in dedupe_keys]
            )
            self.db.commit()

    def add_alert(self, dedupe_key: str, alert: Alert) -> None:
        """Alerts are never updated."""
        with self.lock:
            self._run(
                "INSERT INTO alerts VALUES (?,?,?,?)",
                alert.id,
                dedupe_key,
                alert.account_id,
                alert.model_dump_json(),
            )
            return True

    def next_alert_id(self) -> str:
        return self._next_id("alerts", "ALT")

    def next_case_id(self) -> str:
        return self._next_id("cases", "CASE")

    def add_case(self, alert: Alert) -> None:
        self._run(
            "INSERT INTO cases VALUES (?,?,?,NULL,?)",
            alert.case_id,
            alert.account_id,
            alert.id,
            alert.model_dump_json(),
        )

    def _portfolio_rows(self, table: str, portfolio: str) -> list[dict[str, Any]]:
        return self._all(
            f"SELECT x.* FROM {table} x JOIN accounts a USING (account_id) WHERE a.portfolio=?",
            portfolio,
        )

    def all_alerts(self) -> list[Alert]:
        return [Alert.model_validate_json(r["body"]) for r in self._all("SELECT body FROM alerts")]

    def add_case_link(self, link: CaseLink) -> None:
        self._run(
            "INSERT INTO case_links (alert_id, case_id, action, body) VALUES (?,?,?,?)",
            link.alert_id,
            link.case_id,
            link.action,
            link.model_dump_json(),
        )

    def case_links(self, case_id: str) -> list[CaseLink]:
        rows = self._all("SELECT body FROM case_links WHERE case_id=? ORDER BY seq", case_id)
        return [CaseLink.model_validate_json(r["body"]) for r in rows]

    def separated_alert_ids(self) -> set[str]:
        """Consolidation leaves these alone, so an Analyst's separation lasts."""
        rows = self._all("SELECT DISTINCT alert_id FROM case_links WHERE action='separated'")
        return {r["alert_id"] for r in rows}

    def worked_case_ids(self) -> set[str]:
        rows = self._all(
            "SELECT case_id FROM decisions UNION SELECT case_id FROM notes "
            "UNION SELECT case_id FROM classifications "
            "UNION SELECT id FROM cases WHERE investigation_id IS NOT NULL"
        )
        return {r["case_id"] for r in rows}

    def _memberships(self, alerts: list[Alert]) -> dict[str, str | None]:
        links = self._all("SELECT alert_id, case_id, action FROM case_links ORDER BY seq")
        latest = {r["alert_id"]: r for r in links}
        homes: dict[str, str | None] = {}
        for alert in alerts:
            link = latest.get(alert.id)
            homes[alert.id] = link["case_id"] if link and link["action"] == "grouped" else alert.case_id
        return homes

    def memberships(self) -> dict[str, str | None]:
        """Alert ID to the Case holding it now. The Alert itself keeps its original case_id."""
        return self._memberships(self.all_alerts())

    def _case_alerts(self) -> tuple[dict[str, list[Alert]], dict[str, str | None]]:
        alerts = self.all_alerts()
        homes = self._memberships(alerts)
        members: dict[str, list[Alert]] = defaultdict(list)
        for alert in sorted(alerts, key=lambda a: (-a.score, a.id)):
            if homes[alert.id]:
                members[homes[alert.id]].append(alert)
        return members, homes

    def case_alerts(self, case_id: str) -> list[Alert]:
        return self._case_alerts()[0].get(case_id, [])

    def add_note(self, case_id: str, note: Note) -> None:
        self._run("INSERT INTO notes VALUES (?,?)", case_id, note.model_dump_json())

    def notes(self, case_id: str) -> list[Note]:
        rows = self._all("SELECT body FROM notes WHERE case_id=? ORDER BY rowid", case_id)
        return [Note.model_validate_json(r["body"]) for r in rows]

    def add_classification(self, case_id: str, item: Classification) -> None:
        self._run("INSERT INTO classifications VALUES (?,?)", case_id, item.model_dump_json())

    def classifications(self, case_id: str) -> list[Classification]:
        rows = self._all("SELECT body FROM classifications WHERE case_id=? ORDER BY rowid", case_id)
        return [Classification.model_validate_json(r["body"]) for r in rows]

    def alerts(self, portfolio: str) -> list[Alert]:
        rows = self._portfolio_rows("alerts", portfolio)
        alerts = [Alert.model_validate_json(r["body"]) for r in rows]
        return sorted(alerts, key=lambda a: (-a.score, a.id))

    def get_alert(self, alert_id: str) -> Alert | None:
        row = self._one("SELECT body FROM alerts WHERE id=?", alert_id)
        return Alert.model_validate_json(row["body"]) if row else None

    def decisions(self, case_id: str) -> list[Decision]:
        rows = self._all("SELECT body FROM decisions WHERE case_id=? ORDER BY rowid", case_id)
        return [Decision.model_validate_json(r["body"]) for r in rows]

    def add_decision(self, case_id: str, decision: Decision) -> None:
        self._run("INSERT INTO decisions VALUES (?,?)", case_id, decision.model_dump_json())

    def _case(self, row: dict[str, Any], grouping=None, config=None) -> Case:
        alert = Alert.model_validate_json(row["body"])
        members, homes = grouping or self._case_alerts()
        alerts = members.get(row["id"]) or [alert]
        changes = self.classifications(row["id"])
        original = max((a.risk_level for a in alerts), key=RISK_ORDER.__getitem__)
        classified = changes[-1].risk_level if changes else None
        home = homes.get(alert.id)
        decisions = self.decisions(row["id"])
        investigation = None
        if row["investigation_id"]:
            investigation = self._one(
                "SELECT status FROM investigations WHERE id=?", row["investigation_id"]
            )
        status = "new"
        if investigation:
            status = "investigating" if investigation["status"] == "running" else "report_ready"
        outcomes = [d.decision for d in decisions if d.decision not in RECOMMENDATIONS]
        if outcomes and outcomes[-1] in FINAL_DECISIONS:
            status = "decided"
        elif outcomes and outcomes[-1] == "information_requested":
            status = "awaiting_information"
        return Case(
            id=row["id"],
            alert_id=row["alert_id"],
            customer_id=alert.customer_id,
            account_id=alert.account_id,
            category=alert.category,
            risk_level=classified or original,
            original_risk_level=original,
            supporting_records=alert.supporting_records,
            status=status,
            decisions=decisions,
            investigation_id=row["investigation_id"],
            alert_ids=[a.id for a in alerts],
            products=sorted({a.product for a in alerts}),
            priority=assess(alerts, classified, config or load_config()),
            merged_into=home if home != row["id"] else None,
        )

    def cases(self, portfolio: str) -> list[Case]:
        """Priority order, open work first. A Case consolidated into another isn't listed."""
        grouping, config = self._case_alerts(), load_config()
        rows = [self._case(r, grouping, config) for r in self._portfolio_rows("cases", portfolio)]
        rows = [c for c in rows if c.merged_into is None]
        return sorted(rows, key=lambda c: (c.status == "decided", -c.priority.score, c.id))

    def get_case(self, case_id: str) -> Case | None:
        row = self._one("SELECT * FROM cases WHERE id=?", case_id)
        return self._case(row) if row else None

    def case_detail(self, case_id: str) -> CaseDetail | None:
        case = self.get_case(case_id)
        if case is None:
            return None
        report = self.get_report(case.investigation_id) if case.investigation_id else None
        return CaseDetail(
            case=case,
            alert=self.get_alert(case.alert_id),
            alerts=self.case_alerts(case_id),
            notes=self.notes(case_id),
            classifications=self.classifications(case_id),
            links=self.case_links(case_id),
            report=report,
        )

    def stats(self, portfolio: str) -> Stats:
        alerts = self.alerts(portfolio)
        counts = [
            self._one(f"SELECT COUNT(*) AS n FROM {t}")["n"]
            for t in ("accounts", "transactions", "logins", "loan_applications", "policies", "claims")
        ]
        risk = {"low": 0, "medium": 0, "high": 0}
        categories: dict[str, int] = defaultdict(int)
        for alert in alerts:
            risk[alert.risk_level] += 1
            categories[alert.category] += 1
        return Stats(
            records_processed=sum(counts),
            flagged_events=len(alerts),
            risk_distribution=risk,
            fraud_categories=dict(categories),
        )

    # Investigations
    def start_investigation(self, case_id: str) -> str:
        with self.lock:
            # Traces are seeded from this ID, so it must stay unique across demo resets.
            investigation_id = f"{self._next_id('investigations', 'INV')}-{uuid4().hex[:6]}"
            self._run(
                "INSERT INTO investigations (id, case_id, status) VALUES (?,?,'running')",
                investigation_id,
                case_id,
            )
            self._run(
                "UPDATE cases SET investigation_id=? WHERE id=?", investigation_id, case_id
            )
            return investigation_id

    def remove_investigation(self, investigation_id: str) -> None:
        with self.lock:
            for table, column in [
                ("evidence", "investigation_id"),
                ("steps", "investigation_id"),
                ("follow_ups", "investigation_id"),
                ("investigations", "id"),
            ]:
                self.db.execute(f"DELETE FROM {table} WHERE {column}=?", (investigation_id,))
            self.db.execute(
                "UPDATE cases SET investigation_id=NULL WHERE investigation_id=?",
                (investigation_id,),
            )
            self.db.commit()

    def running_investigations(self) -> list[str]:
        return [r["id"] for r in self._all("SELECT id FROM investigations WHERE status='running'")]

    def mark_replay(self, investigation_id: str, captured_at: str, trace_url: str | None) -> None:
        self._run(
            "UPDATE investigations SET is_replay=1, replay_captured_at=?, trace_url=? WHERE id=?",
            captured_at,
            trace_url,
            investigation_id,
        )

    def get_alert_for_investigation(self, investigation_id: str) -> Alert:
        row = self._one(
            "SELECT c.body FROM investigations i JOIN cases c ON c.id=i.case_id WHERE i.id=?",
            investigation_id,
        )
        return Alert.model_validate_json(row["body"])

    def investigation_status(self, investigation_id: str) -> str | None:
        row = self._one("SELECT status FROM investigations WHERE id=?", investigation_id)
        return row["status"] if row else None

    def get_investigation(self, investigation_id: str) -> Investigation | None:
        row = self._one("SELECT * FROM investigations WHERE id=?", investigation_id)
        if row is None:
            return None
        return Investigation(
            id=row["id"],
            case_id=row["case_id"],
            status=row["status"],
            report=self.get_report(investigation_id),
            evidence=self.list_evidence(investigation_id),
            follow_ups=self.list_follow_ups(investigation_id),
            trace_url=row["trace_url"],
            is_replay=bool(row["is_replay"]),
            replay_captured_at=row["replay_captured_at"],
        )

    def append_step(
        self,
        investigation_id: str,
        stage: str,
        type: str,
        summary: str,
        evidence_ids: Sequence[str] = (),
    ) -> None:
        with self.lock:
            seq = self._one(
                "SELECT COUNT(*) AS n FROM steps WHERE investigation_id=?", investigation_id
            )["n"] + 1
            step = Step(
                seq=seq,
                stage=stage,
                type=type,
                summary=summary,
                evidence_ids=list(evidence_ids),
                at=now(),
            )
            self._run(
                "INSERT INTO steps VALUES (?,?,?)", investigation_id, seq, step.model_dump_json()
            )

    def steps(self, investigation_id: str, after: int = 0) -> list[Step]:
        rows = self._all(
            "SELECT body FROM steps WHERE investigation_id=? AND seq>? ORDER BY seq",
            investigation_id,
            after,
        )
        return [Step.model_validate_json(r["body"]) for r in rows]

    def add_evidence(
        self,
        investigation_id: str,
        kind: str,
        source_ref: str,
        data: dict[str, Any],
        tool_call_id: str | None = None,
    ) -> Evidence:
        with self.lock:
            existing = self._one(
                "SELECT body FROM evidence WHERE investigation_id=? AND kind=? AND source_ref=?",
                investigation_id,
                kind,
                source_ref,
            )
            if existing:
                return Evidence.model_validate_json(existing["body"])
            count = self._one(
                "SELECT COUNT(*) AS n FROM evidence WHERE investigation_id=?", investigation_id
            )["n"]
            row = Evidence(
                id=f"EV-{count + 1}",
                investigation_id=investigation_id,
                kind=kind,
                source_ref=source_ref,
                data=data,
                tool_call_id=tool_call_id,
                collected_at=now(),
            )
            self._run(
                "INSERT INTO evidence VALUES (?,?,?,?,?)",
                row.id,
                investigation_id,
                kind,
                source_ref,
                row.model_dump_json(),
            )
            return row

    def list_evidence(self, investigation_id: str) -> list[Evidence]:
        rows = self._all(
            "SELECT body FROM evidence WHERE investigation_id=? ORDER BY rowid", investigation_id
        )
        return [Evidence.model_validate_json(r["body"]) for r in rows]

    def get_report(self, investigation_id: str) -> Report | None:
        row = self._one("SELECT report FROM investigations WHERE id=?", investigation_id)
        return Report.model_validate_json(row["report"]) if row and row["report"] else None

    def save_report(self, investigation_id: str, report: Report) -> None:
        self._run(
            "UPDATE investigations SET report=?, status='complete' WHERE id=?",
            report.model_dump_json(),
            investigation_id,
        )

    def trace_url(self, investigation_id: str) -> str | None:
        row = self._one("SELECT trace_url FROM investigations WHERE id=?", investigation_id)
        return row["trace_url"] if row else None

    def set_trace_url(self, investigation_id: str, url: str) -> None:
        self._run("UPDATE investigations SET trace_url=? WHERE id=?", url, investigation_id)

    def add_follow_up(self, investigation_id: str, question: str) -> FollowUp:
        with self.lock:
            row = FollowUp(
                id=self._next_id("follow_ups", "FUP"), question=question, asked_at=now()
            )
            self._run(
                "INSERT INTO follow_ups VALUES (?,?,?)",
                row.id,
                investigation_id,
                row.model_dump_json(),
            )
            return row

    def get_follow_up(self, follow_up_id: str) -> FollowUp:
        row = self._one("SELECT body FROM follow_ups WHERE id=?", follow_up_id)
        return FollowUp.model_validate_json(row["body"])

    def list_follow_ups(self, investigation_id: str) -> list[FollowUp]:
        rows = self._all(
            "SELECT body FROM follow_ups WHERE investigation_id=? ORDER BY rowid", investigation_id
        )
        return [FollowUp.model_validate_json(r["body"]) for r in rows]

    def pending_follow_ups(self) -> list[str]:
        rows = self._all("SELECT id, body FROM follow_ups")
        return [r["id"] for r in rows if FollowUp.model_validate_json(r["body"]).answer is None]

    def save_followup_answer(
        self, follow_up_id: str, answer: str, evidence_ids: Sequence[str], verification: str
    ) -> None:
        row = self.get_follow_up(follow_up_id)
        row.answer, row.evidence_ids, row.verification = answer, list(evidence_ids), verification
        self._run("UPDATE follow_ups SET body=? WHERE id=?", row.model_dump_json(), follow_up_id)

    def _audit_portfolio(self, details: dict[str, Any]) -> str | None:
        analyst = self.analyst(details.get("analyst_id"))
        if analyst:
            return analyst.portfolio
        row = self._one(
            "SELECT a.portfolio FROM investigations i JOIN cases c ON c.id=i.case_id "
            "JOIN accounts a ON a.account_id=c.account_id WHERE i.id=?",
            details.get("investigation_id"),
        )
        return row["portfolio"] if row else None

    def audit(self, event: str, **details: Any) -> None:
        details["portfolio"] = self._audit_portfolio(details) or details.get("portfolio")
        self._run(
            "INSERT INTO audit (event, at, details) VALUES (?,?,?)",
            event,
            now(),
            json.dumps(details, default=str),
        )

    def audit_trail(self, portfolio: str) -> list[dict[str, Any]]:
        rows = self._all("SELECT * FROM audit ORDER BY seq DESC")
        parsed = [{**r, "details": json.loads(r["details"])} for r in rows]
        return [r for r in parsed if r["details"].get("portfolio") == portfolio][:500]
