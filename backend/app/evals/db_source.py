"""Evals on a private in-memory copy of the sample data, so demo data is never touched."""

import json
from pathlib import Path

from contracts import AnalystScope
from correlation.consolidate import consolidate
from demo.generator import generate
from demo.seed import load_rows
from detection.engine import load_config, persist, scan
from store import Store

from .metrics import detection_metrics
from .sweep import run_sweep

HELD_OUT = Path(__file__).with_name("held_out.json")  # frozen, so new stories can't change it
SCENARIOS = {
    "account_takeover": "TXN-50001",
    "false_positive": "TXN-50002",
    "loan_diversion": "TXN-50003",
}


class CaseView:
    """Points one Investigation at one Case on the shared eval store."""

    def __init__(self, store: Store, case_id: str):
        self._store = store
        self._case_id = case_id

    def __getattr__(self, name):
        return getattr(self._store, name)

    def get_alert_for_investigation(self, investigation_id):
        self._store._run(
            "INSERT OR IGNORE INTO investigations (id, case_id, status) VALUES (?,?,'running')",
            investigation_id,
            self._case_id,
        )
        return self._store.get_alert_for_investigation(investigation_id)


class DbSource:
    scope = AnalystScope(analyst_id="analyst-1", portfolio="portfolio-1")

    def __init__(self):
        self.store = self._fresh()
        self.config = load_config()
        self.candidates = scan(self.store.detection_inputs(), self.config)
        persist(self.store, self.candidates, self.config)
        consolidate(self.store, self.config)
        self.alerts = self.store.alerts("portfolio-1")
        other = next(
            a for a in generate().customers
            if a["portfolio"] == "portfolio-2" and self._wholly_out_of_scope(a["device"])
        )
        self.out_of_scope_account = other["account_id"]
        self.out_of_scope_device = other["device"]
        self.out_of_scope_beneficiary = next(
            row["beneficiary_id"]
            for row in self.store.detection_inputs()["transactions"]
            if self.store.beneficiary_portfolios(row["beneficiary_id"]) == {"portfolio-2"}
        )

    def _wholly_out_of_scope(self, device_id: str) -> bool:
        """One customer can hold accounts in both Portfolios, which shares their device."""
        device = self.store.get_device(device_id)
        return device is not None and all(
            self.store.account_portfolio(a) != self.scope.portfolio for a in device["accounts"]
        )

    @staticmethod
    def _fresh() -> Store:
        store = Store()
        load_rows(store, generate())
        return store

    def _case_for(self, transaction_id: str, store: Store | None = None) -> CaseView:
        store = store or self.store
        alert = next(a for a in store.alerts("portfolio-1") if a.transaction_id == transaction_id)
        case = store.get_case(alert.case_id)
        return CaseView(store, case.merged_into or case.id)  # as an Analyst would reach it

    def scenario(self, name):
        return self._case_for(SCENARIOS[name])

    def poisoned(self, field, text):
        store = self._fresh()
        persist(store, scan(store.detection_inputs(), self.config), self.config)
        consolidate(store, self.config)
        if field == "details":
            store._run("UPDATE account_events SET details=? WHERE account_id='ACC-10042' "
                       "AND type='device_enrolled'", text)
        else:
            store._run(f"UPDATE transactions SET {field}=? WHERE transaction_id='TXN-50001'", text)
        return self._case_for("TXN-50001", store)

    def held_out(self):
        return [
            (row["transaction_id"], self._case_for(row["transaction_id"]), row["expected"])
            for row in json.loads(HELD_OUT.read_text())
        ]

    def sweep(self):
        held = {row["transaction_id"] for row in json.loads(HELD_OUT.read_text())}
        return run_sweep(self.store, held)

    def denial_store(self):
        return self.store

    def detection(self):
        actionable = self.config["thresholds"]["actionable"]
        flagged = {c.subject_id for c in self.candidates if c.score >= actionable}
        return detection_metrics(
            {"flagged": g["subject_id"] in flagged, "is_fraud": bool(g["is_fraud"]), "story": g["story"]}
            for g in self.store.ground_truth()
        )
