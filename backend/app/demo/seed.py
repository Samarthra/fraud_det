"""Loads the sample data and runs detection."""

from datetime import datetime, timedelta

from demo.generator import generate
from detection.engine import load_config, persist, scan

BACKLOG_DAYS = 7
BACKLOG_PER_ANALYST = 25
MUST_SHOW = {"TXN-50001", "TXN-50002"}


def load_rows(store, sample) -> None:
    for dataset in ("customers", "transactions", "logins", "loan_applications"):
        store.insert_rows(dataset, getattr(sample, dataset))
    store.insert_events(sample.account_events)
    store.insert_ground_truth(sample.ground_truth)


def backlog(candidates, config, now, portfolios):
    """All recent Low alerts, and only the top actionable ones per Analyst."""
    since = now - timedelta(days=BACKLOG_DAYS)
    actionable = config["thresholds"]["actionable"]
    recent = [c for c in candidates if datetime.fromisoformat(c.at) >= since or c.subject_id in MUST_SHOW]
    kept = [c for c in recent if c.score < actionable]
    # Take from each category in turn, so high scorers can't crowd one out.
    rank: dict[tuple[str, str], int] = {}
    order = []
    for c in sorted(recent, key=lambda x: -x.score):
        if c.score >= actionable:
            key = (portfolios[c.account_id], c.category)
            rank[key] = rank.get(key, 0) + 1
            order.append((c.subject_id not in MUST_SHOW, rank[key], -c.score, len(order), c))
    per_analyst: dict[str, int] = {}
    for *_, c in sorted(order, key=lambda row: row[:4]):
        portfolio = portfolios[c.account_id]
        if per_analyst.get(portfolio, 0) < BACKLOG_PER_ANALYST or c.subject_id in MUST_SHOW:
            per_analyst[portfolio] = per_analyst.get(portfolio, 0) + 1
            kept.append(c)
    return kept


def load_sample(store, now: datetime | None = None) -> int:
    sample = generate(now)
    load_rows(store, sample)
    config = load_config()
    candidates = scan(store.detection_inputs(), config)
    portfolios = {r["account_id"]: r["portfolio"] for r in sample.customers}
    reference = now or datetime.now().astimezone()
    kept = backlog(candidates, config, reference, portfolios)
    shown = {c.dedupe_key for c in kept}
    store.add_baseline([c.dedupe_key for c in candidates if c.dedupe_key not in shown])
    return persist(store, kept, config)
