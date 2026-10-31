"""SQLite schema, writes and read-only query helpers. Implements agent.ports.AgentStore."""

import json
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Sequence
from uuid import uuid4

from contracts import (
    Alert,
    Analyst,
    Case,
    CaseDetail,
    Decision,
    Evidence,
    FollowUp,
    Investigation,
    Report,
    Stats,
    Step,
)

ANALYSTS = [
    Analyst(id="analyst-1", name="Asha Menon", portfolio="portfolio-1"),
    Analyst(id="analyst-2", name="Ravi Iyer", portfolio="portfolio-2"),
]
FINAL_DECISIONS = {"false_positive", "confirmed_fraud", "escalated"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (account_id TEXT PRIMARY KEY, customer_id TEXT, name TEXT,
  phone TEXT, email TEXT, address TEXT, onboarded_at TEXT, portfolio TEXT);
CREATE TABLE IF NOT EXISTS transactions (transaction_id TEXT PRIMARY KEY, account_id TEXT,
  beneficiary_id TEXT, beneficiary_name TEXT, amount REAL, timestamp TEXT, channel TEXT,
  status TEXT, device_id TEXT, ip_country TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS logins (login_id TEXT PRIMARY KEY, account_id TEXT, customer_id TEXT,
  device_id TEXT, ip TEXT, timestamp TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS loan_applications (application_id TEXT PRIMARY KEY, customer_id TEXT,
  device_id TEXT, amount REAL, status TEXT, timestamp TEXT);
CREATE TABLE IF NOT EXISTS account_events (account_id TEXT, type TEXT, at TEXT, details TEXT);
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
    "decisions investigations evidence steps follow_ups counters baseline"
).split()
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
        "application_id customer_id device_id amount status timestamp",
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

    def insert_events(self, rows: list[dict[str, Any]]) -> None:
        with self.lock:
            self.db.executemany(
                "INSERT INTO account_events VALUES (?,?,?,?)",
                [(r["account_id"], r["type"], r["at"], r["details"]) for r in rows],
            )
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
            "own_account_id": {
                r["account_id"]
                for r in self._all("SELECT account_id FROM accounts WHERE portfolio=?", portfolio)
            },
            "own_customer_id": {
                r["customer_id"]
                for r in self._all("SELECT customer_id FROM accounts WHERE portfolio=?", portfolio)
            },
        }

    def detection_inputs(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "accounts": self._all("SELECT * FROM accounts"),
            "transactions": self._all("SELECT * FROM transactions ORDER BY timestamp"),
            "logins": self._all("SELECT * FROM logins ORDER BY timestamp"),
            "loans": self._all("SELECT * FROM loan_applications ORDER BY timestamp"),
        }

    # Query helpers used by tools
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
        events = self._all("SELECT * FROM account_events WHERE account_id=?", account_id)
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

    def _case(self, row: dict[str, Any]) -> Case:
        alert = Alert.model_validate_json(row["body"])
        decisions = self.decisions(row["id"])
        investigation = None
        if row["investigation_id"]:
            investigation = self._one(
                "SELECT status FROM investigations WHERE id=?", row["investigation_id"]
            )
        status = "new"
        if investigation:
            status = "investigating" if investigation["status"] == "running" else "report_ready"
        if decisions and decisions[-1].decision in FINAL_DECISIONS:
            status = "decided"
        return Case(
            id=row["id"],
            alert_id=row["alert_id"],
            customer_id=alert.customer_id,
            account_id=alert.account_id,
            category=alert.category,
            risk_level=alert.risk_level,
            supporting_records=alert.supporting_records,
            status=status,
            decisions=decisions,
            investigation_id=row["investigation_id"],
        )

    def cases(self, portfolio: str) -> list[Case]:
        return [self._case(r) for r in self._portfolio_rows("cases", portfolio)]

    def get_case(self, case_id: str) -> Case | None:
        row = self._one("SELECT * FROM cases WHERE id=?", case_id)
        return self._case(row) if row else None

    def case_detail(self, case_id: str) -> CaseDetail | None:
        case = self.get_case(case_id)
        if case is None:
            return None
        report = self.get_report(case.investigation_id) if case.investigation_id else None
        return CaseDetail(case=case, alert=self.get_alert(case.alert_id), report=report)

    def stats(self, portfolio: str) -> Stats:
        alerts = self.alerts(portfolio)
        counts = [
            self._one(f"SELECT COUNT(*) AS n FROM {t}")["n"]
            for t in ("accounts", "transactions", "logins", "loan_applications")
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
        details["portfolio"] = self._audit_portfolio(details)
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
