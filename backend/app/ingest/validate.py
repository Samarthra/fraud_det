"""Check rows against a dataset. Nothing is dropped without a reason."""

from collections.abc import Collection, Mapping
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from contracts import RejectedRow

from .parse import OVERFLOW
from .schema import DEFAULT_PORTFOLIO, Column, Dataset

IST = timezone(timedelta(hours=5, minutes=30))


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def validate_rows(
    dataset: Dataset,
    rows: list[tuple[int, Any]],
    known_ids: Mapping[str, Collection[str]],
) -> tuple[list[dict[str, Any]], list[RejectedRow], int]:
    """Returns valid rows, rejected rows and the count of fully blank rows."""
    valid: list[dict[str, Any]] = []
    rejected: list[RejectedRow] = []
    blank = 0
    seen = set(known_ids.get(dataset.primary_key, ()))

    for number, raw in rows:
        if not isinstance(raw, dict):
            rejected.append(RejectedRow(row=number, reasons=["Record is not an object."]))
            continue
        if all(is_blank(v) for v in raw.values()):
            blank += 1
            continue

        clean: dict[str, Any] = {}
        reasons: list[str] = []
        if raw.get(OVERFLOW):
            reasons.append(f"Row has {raw[OVERFLOW]} more value(s) than the header has columns.")
        for column in dataset.columns:
            value, error = _check(column, raw.get(column.name), known_ids)
            clean[column.name] = value
            if error:
                reasons.append(error)

        key = clean.get(dataset.primary_key)
        if key is not None and key in seen:
            reasons.append(f"Duplicate {dataset.primary_key} '{key}'.")

        if reasons:
            rejected.append(RejectedRow(row=number, reasons=reasons))
            continue
        seen.add(key)
        if dataset.name == "customers" and clean["portfolio"] is None:
            clean["portfolio"] = DEFAULT_PORTFOLIO
        valid.append(clean)
    return valid, rejected, blank


def _check(
    column: Column, value: Any, known_ids: Mapping[str, Collection[str]]
) -> tuple[Any, str | None]:
    if is_blank(value):
        return None, f"Missing {column.name}." if column.required else None
    if isinstance(value, (dict, list)):
        return None, f"{column.name} must be a single value."

    match column.kind:
        case "amount":
            return _amount(column, value)
        case "timestamp":
            return _timestamp(column, value)
        case "enum":
            text = str(value).strip().lower()
            if text not in column.choices:
                return None, f"{column.name} must be one of {', '.join(column.choices)}."
            return text, None

    text = str(value).strip()
    if column.links_to and text not in known_ids.get(column.links_to, ()):
        return None, f"Unknown {column.name} '{text}'."
    return text, None


def _amount(column: Column, value: Any) -> tuple[Any, str | None]:
    text = str(value).strip().replace("₹", "").replace(",", "").strip()
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None, f"{column.name} '{value}' is not a number."
    if not amount.is_finite() or amount <= 0:
        return None, f"{column.name} must be greater than 0."
    return float(amount), None


def _timestamp(column: Column, value: Any) -> tuple[Any, str | None]:
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None, f"{column.name} '{value}' is not an ISO date."
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.isoformat(), None
