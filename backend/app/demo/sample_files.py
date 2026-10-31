"""A small upload with deliberate bad rows, for showing validation."""

import csv
import io
from datetime import datetime, timedelta

from demo.generator import generate
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

    # Analyst 1's accounts, because uploads can only touch your own Portfolio.
    own = [a["account_id"] for a in generate(now).customers if a["portfolio"] == "portfolio-1"]
    rows = [row(i, own[i], 1500 + i * 25) for i in range(1, 9)]
    rows += [
        row(9, own[1], ""),
        row(10, "ACC-99999", 1200),
        row(11, own[2], "twelve hundred"),
        row(12, own[3], 1200, "31/10/2026"),
    ]
    out = io.StringIO()
    writer = csv.DictWriter(out, columns)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()
