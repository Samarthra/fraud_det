"""Evals on a private in-memory copy of the sample data, so demo data is never touched."""

import random

from contracts import AnalystScope
from demo.generator import generate
from demo.seed import load_rows
from detection.engine import load_config, persist, scan
from store import Store

from .metrics import detection_metrics

HELD_OUT_SEED = 7
HELD_OUT_EACH = 10
SCENARIOS = {"account_takeover": "TXN-50001", "false_positive": "TXN-50002"}


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
        self.alerts = self.store.alerts("portfolio-1")
        other = next(a for a in generate().customers if a["portfolio"] == "portfolio-2")
        self.out_of_scope_account = other["account_id"]
        self.out_of_scope_device = other["device"]

    @staticmethod
    def _fresh() -> Store:
        store = Store()
        load_rows(store, generate())
        return store

    def _case_for(self, transaction_id: str, store: Store | None = None) -> CaseView:
        store = store or self.store
        alert = next(a for a in store.alerts("portfolio-1") if a.transaction_id == transaction_id)
        return CaseView(store, alert.case_id)

    def scenario(self, name):
        return self._case_for(SCENARIOS[name])

    def poisoned(self, field, text):
        store = self._fresh()
        persist(store, scan(store.detection_inputs(), self.config), self.config)
        store._run(f"UPDATE transactions SET {field}=? WHERE transaction_id='TXN-50001'", text)
        return self._case_for("TXN-50001", store)

    def held_out(self):
        labels = {g["subject_id"]: bool(g["is_fraud"]) for g in self.store.ground_truth()}
        pool = [
            a for a in self.alerts
            if a.case_id and a.transaction_id in labels and a.transaction_id not in SCENARIOS.values()
        ]
        rng = random.Random(HELD_OUT_SEED)
        cases = []
        for is_fraud, want in ((True, "suspicious"), (False, "not_suspicious")):
            group = sorted((a for a in pool if labels[a.transaction_id] == is_fraud), key=lambda a: a.id)
            for alert in rng.sample(group, min(HELD_OUT_EACH, len(group))):
                cases.append((alert.transaction_id, CaseView(self.store, alert.case_id), want))
        return cases

    def denial_store(self):
        return self.store

    def detection(self):
        actionable = self.config["thresholds"]["actionable"]
        flagged = {c.subject_id for c in self.candidates if c.score >= actionable}
        return detection_metrics(
            {"flagged": g["subject_id"] in flagged, "is_fraud": bool(g["is_fraud"]), "story": g["story"]}
            for g in self.store.ground_truth()
        )
