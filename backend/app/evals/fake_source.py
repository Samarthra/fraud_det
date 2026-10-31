"""In-memory scenarios for rehearsing the suite until `store` exists."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "tests"))

from contracts import AnalystScope  # noqa: E402
from fakes import BENIGN, TAKEOVER, FakeStore  # noqa: E402


class FakeSource:
    scope = AnalystScope(analyst_id="a1", portfolio="p1")
    out_of_scope_account = "ACC-60001"
    out_of_scope_device = "DEV-OUT"
    out_of_scope_beneficiary = "BEN-OUT"

    def scenario(self, name):
        return FakeStore(BENIGN if name == "false_positive" else TAKEOVER)

    def poisoned(self, field, text):
        store = FakeStore(TAKEOVER)
        if field == "details":
            store.events["ACC-10042"][-1][field] = text
        else:
            store.transactions["ACC-10042"][0][field] = text
        return store

    def held_out(self):
        return []

    def sweep(self):
        return {"stories": {}, "wrong": []}

    def denial_store(self):
        return FakeStore()

    def detection(self):
        return None
