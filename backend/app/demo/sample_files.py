"""A small upload with deliberate bad rows, for showing validation."""

import csv
import io
from datetime import datetime, timedelta

from ingest import DATASETS

NOTES = ["Missing amount", "Unknown account", "Amount is not a number", "Bad date"]


def bad_rows_csv(now: datetime | None = None) -> str:
    now = now or datetime.now().astimezone()
    columns = DATASETS["transactions"].column_names
    stamp = (now - timedelta(minutes=5)).isoformat(timespec="seconds")

    def row(n, account, amount, when=stamp):
        return {
            "transaction_id": f"TXN-9{n:04d}", "account_id": account, "beneficiary_id": "BEN-10001",
            "beneficiary_name": "Upload Payee", "amount": amount, "timestamp": when,
            "channel": "web", "status": "completed", "device_id": "", "ip_country": "IN",
            "description": "Uploaded batch",
        }

    rows = [row(i, f"ACC-{30000 + i}", 1500 + i * 25) for i in range(1, 9)]
    rows += [
        row(9, "ACC-30001", ""),
        row(10, "ACC-99999", 1200),
        row(11, "ACC-30002", "twelve hundred"),
        row(12, "ACC-30003", 1200, "31/10/2026"),
    ]
    out = io.StringIO()
    writer = csv.DictWriter(out, columns)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()
