"""Upload parsing and validation. The API route inserts rows and runs detection."""

import csv
import io
from collections.abc import Collection, Mapping
from typing import Any

from contracts import UploadResult

from .parse import OVERFLOW, FileRejected, parse_file
from .schema import DATASETS
from .validate import validate_rows

__all__ = ["DATASETS", "FileRejected", "check_file", "template_csv"]


def check_file(
    dataset_name: str,
    filename: str,
    content: bytes,
    known_ids: Mapping[str, Collection[str]],
) -> tuple[list[dict[str, Any]], UploadResult]:
    """Returns rows that are safe to insert, and the report to show the Analyst.

    known_ids maps `account_id`, `customer_id` and each dataset's primary key to
    the values already stored. The caller sets `alerts_created` after detection.
    """
    dataset = DATASETS.get(dataset_name)
    if dataset is None:
        raise FileRejected(f"Unknown dataset '{dataset_name}'.")

    rows = parse_file(filename, content)
    headers = {k for _, row in rows if isinstance(row, dict) for k in row} - {OVERFLOW}
    required = [c.name for c in dataset.columns if c.required]
    missing = [name for name in required if name not in headers]
    if missing:
        raise FileRejected(f"Missing required column(s): {', '.join(missing)}.")

    valid, rejected, blank = validate_rows(dataset, rows, known_ids)
    return valid, UploadResult(
        dataset=dataset_name,
        filename=filename,
        total_rows=len(rows) - blank,
        loaded=len(valid),
        rejected=rejected,
        ignored_columns=sorted(headers - set(dataset.column_names)),
        blank_rows=blank,
    )


def template_csv(dataset_name: str) -> str:
    out = io.StringIO()
    csv.writer(out).writerow(DATASETS[dataset_name].column_names)
    return out.getvalue()
